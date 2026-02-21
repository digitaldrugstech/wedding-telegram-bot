"""Clan war — weekly gang competition with activity scoring."""

import html
from datetime import datetime, timedelta

import structlog
from sqlalchemy import func
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import CasinoGame, Duel, Gang, GangMember, InterpolFine, Job, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_word

logger = structlog.get_logger()

# Points per activity type
POINTS = {
    "active_worker": 3,  # Per member who worked this week (Job.last_work_time in range)
    "casino_win": 2,  # Per casino win
    "duel_win": 5,  # Per duel won
    "fine_given": 3,  # Per interpol fine given
    "raid_success": 20,  # Per successful raid (future integration)
}

CLANWAR_PRIZE_POOL = 5000  # Base prize pool per week (added to total gang earnings)
CLANWAR_BONUS_PER_MEMBER = 500  # Bonus per member in winning gang


def get_week_boundaries():
    """Get start and end of current week (Monday 00:00 UTC to Sunday 23:59 UTC)."""
    now = datetime.utcnow()
    # Start of this week (Monday)
    start = now - timedelta(days=now.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    # End of this week (Sunday)
    end = start + timedelta(days=7)
    return start, end


def calculate_gang_score(db, gang_id: int, week_start: datetime, week_end: datetime) -> dict:
    """Calculate total score for a gang this week."""
    # Get all member user_ids
    members = db.query(GangMember.user_id).filter(GangMember.gang_id == gang_id).all()
    member_ids = [m[0] for m in members]

    if not member_ids:
        return {"total": 0, "work": 0, "casino": 0, "duels": 0, "fines": 0, "members": 0}

    # Count active workers this week (members who did at least one /job)
    active_workers = (
        db.query(func.count(Job.id))
        .filter(
            Job.user_id.in_(member_ids),
            Job.last_work_time >= week_start,
            Job.last_work_time < week_end,
        )
        .scalar()
        or 0
    )

    # Count casino wins this week
    casino_wins = (
        db.query(func.count(CasinoGame.id))
        .filter(
            CasinoGame.user_id.in_(member_ids),
            CasinoGame.result == "win",
            CasinoGame.played_at >= week_start,
            CasinoGame.played_at < week_end,
        )
        .scalar()
        or 0
    )

    # Count duel wins this week
    duel_wins = (
        db.query(func.count(Duel.id))
        .filter(
            Duel.winner_id.in_(member_ids),
            Duel.completed_at >= week_start,
            Duel.completed_at < week_end,
        )
        .scalar()
        or 0
    )

    # Count interpol fines given
    fines_given = (
        db.query(func.count(InterpolFine.id))
        .filter(
            InterpolFine.interpol_id.in_(member_ids),
            InterpolFine.created_at >= week_start,
            InterpolFine.created_at < week_end,
        )
        .scalar()
        or 0
    )

    # Calculate total score
    total = (
        active_workers * POINTS["active_worker"]
        + casino_wins * POINTS["casino_win"]
        + duel_wins * POINTS["duel_win"]
        + fines_given * POINTS["fine_given"]
    )

    return {
        "total": total,
        "workers": active_workers,
        "casino": casino_wins,
        "duels": duel_wins,
        "fines": fines_given,
        "members": len(member_ids),
    }


@require_registered
async def clanwar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clanwar — show weekly gang competition standings."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    week_start, week_end = get_week_boundaries()

    with get_db() as db:
        # Get all gangs
        gangs = db.query(Gang).all()

        if not gangs:
            await update.message.reply_text(
                "⚔️ <b>Война кланов</b>\n\nПока нет банд\n\n/gang create [название] — создать первую!",
                parse_mode="HTML",
            )
            return

        # Calculate scores for all gangs
        gang_scores = []
        for gang in gangs:
            score = calculate_gang_score(db, gang.id, week_start, week_end)
            leader = db.query(User).filter(User.telegram_id == gang.leader_id).first()
            leader_name = leader.username if leader else f"ID {gang.leader_id}"

            gang_scores.append(
                {
                    "id": gang.id,
                    "name": html.escape(gang.name),
                    "level": gang.level,
                    "leader": html.escape(str(leader_name)),
                    **score,
                }
            )

        # Sort by total score
        gang_scores.sort(key=lambda x: x["total"], reverse=True)

        # Check which gang user belongs to
        user_member = db.query(GangMember).filter(GangMember.user_id == user_id).first()
        user_gang_id = user_member.gang_id if user_member else None

    # Build leaderboard
    days_left = (week_end - datetime.utcnow()).days
    hours_left = int((week_end - datetime.utcnow()).total_seconds() % 86400 / 3600)

    text = (
        f"⚔️ <b>Война кланов</b>\n\n"
        f"📅 Эта неделя ({week_start.strftime('%d.%m')} - {(week_end - timedelta(days=1)).strftime('%d.%m')})\n"
        f"⏰ До конца: {days_left}д {hours_left}ч\n\n"
    )

    if gang_scores and gang_scores[0]["total"] > 0:
        text += (
            f"🏆 Призовой фонд: {format_diamonds(CLANWAR_PRIZE_POOL)}"
            f" + {format_diamonds(CLANWAR_BONUS_PER_MEMBER)}/чел\n\n"
        )

    for i, gs in enumerate(gang_scores[:10], 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        marker = " 👈" if gs["id"] == user_gang_id else ""

        text += (
            f"{medal} <b>{gs['name']}</b> (ур.{gs['level']}) —"
            f" {format_word(gs['total'], 'очко', 'очка', 'очков')}{marker}\n"
            f"   💼{gs['workers']} 🎰{gs['casino']} ⚔️{gs['duels']} 🚔{gs['fines']} | 👥{gs['members']}\n\n"
        )

    if not gang_scores or all(gs["total"] == 0 for gs in gang_scores):
        text += "<i>Пока никто не набрал очков на этой неделе</i>\n\n"

    text += (
        "<b>Как зарабатывать очки:</b>\n"
        f"💼 Работники: +{POINTS['active_worker']} за каждого, кто работал\n"
        f"🎰 Казино (выигрыш): +{POINTS['casino_win']}\n"
        f"⚔️ Дуэль (победа): +{POINTS['duel_win']}\n"
        f"🚔 Штраф (интерпол): +{POINTS['fine_given']}\n\n"
        "Победители получают призы в понедельник!"
    )

    if not user_gang_id:
        text += "\n\n💡 <i>Ты не в банде — /gang create [название]</i>"

    await update.message.reply_text(text, parse_mode="HTML")


def register_clanwar_handlers(application):
    """Register clan war handlers."""
    application.add_handler(CommandHandler(["clanwar", "cw"], clanwar_command))
    logger.info("Clan war handlers registered")
