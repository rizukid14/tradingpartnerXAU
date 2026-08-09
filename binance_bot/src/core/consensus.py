"""
Consensus 2 proposer + 1 approver.

1. GPT + Gemini vote paralel (BUY/HOLD karena spot).
2. Kalau 2/2 sepakat BUY & skor confidence >= threshold → panggil Claude approver.
3. HOLD-streak: kalau N cycle berturut-turut HOLD, cukup 1 BUY kuat
   (conf >= config.HOLD_STREAK_BUY_CONFIDENCE) → lanjut approver.
   Mencegah satu proposer konservatif memblokir selamanya.
4. Claude approve → signal eksekusi. Reject / beda pendapat → HOLD.
"""
import logging

import config

log = logging.getLogger("binance_bot")


def calculate_consensus(proposals, hold_streak=0):
    """
    proposals: dict dari get_proposals() → {model: {signal, confidence, sl_pct, tp_pct, reasoning}}
    hold_streak: jumlah cycle HOLD beruntun (dari RiskEngine).
    Return dict:
      {approved, signal, score, threshold, sl_pct, tp_pct, reasoning, models}
    """
    models = list(proposals.keys())
    # Skor per arah: hanya BUY yang relevan (spot). SELL tanpa posisi = hold.
    buy_score = 0.0
    buy_models = []
    hold_models = []
    sl_pcts, tp_pcts = [], []

    for name, p in proposals.items():
        sig = p.get("signal", "HOLD")
        conf = p.get("confidence", 0.0)
        if sig == "BUY":
            buy_score += conf
            buy_models.append(name)
            if p.get("sl_pct") is not None:
                sl_pcts.append(float(p["sl_pct"]))
            if p.get("tp_pct") is not None:
                tp_pcts.append(float(p["tp_pct"]))
        else:
            hold_models.append(name)

    threshold = config.CONFIDENCE_THRESHOLD
    streak_active = hold_streak >= config.HOLD_STREAK_THRESHOLD
    buy_confirmed = False
    reasoning = ""

    # Mode 1: 2/2 proposer sepakat BUY + skor >= threshold
    if len(buy_models) >= 2 and buy_score >= threshold:
        buy_confirmed = True
        reasoning = f"2/2 proposer sepakat BUY (skor {buy_score:.2f})"
    # Mode 2 (HOLD-streak): 1 BUY kuat cukup — Claude approver jadi penyeimbang
    elif streak_active and len(buy_models) >= 1:
        best_conf = max(p.get("confidence", 0.0) for p in proposals.values()
                        if p.get("signal") == "BUY")
        if best_conf >= config.HOLD_STREAK_BUY_CONFIDENCE:
            buy_confirmed = True
            # Pakai SL/TP dari proposer BUY (yang punya conf tertinggi)
            best_proposal = max(
                (p for p in proposals.values() if p.get("signal") == "BUY"),
                key=lambda p: p.get("confidence", 0.0))
            if best_proposal.get("sl_pct") is not None:
                sl_pcts = [float(best_proposal["sl_pct"])]
            if best_proposal.get("tp_pct") is not None:
                tp_pcts = [float(best_proposal["tp_pct"])]
            reasoning = (f"HOLD-streak {hold_streak} -> 1 BUY kuat cukup "
                         f"(conf {best_conf:.2f} >= {config.HOLD_STREAK_BUY_CONFIDENCE})")

    if buy_confirmed:
        sl_pct = sum(sl_pcts) / len(sl_pcts) if sl_pcts else config.DEFAULT_SL_PCT
        tp_pct = sum(tp_pcts) / len(tp_pcts) if tp_pcts else config.DEFAULT_TP_PCT
        return {
            "approved": True,
            "signal": "BUY",
            "score": round(buy_score, 2),
            "threshold": threshold,
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "reasoning": reasoning,
            "models": buy_models,
        }
    return {
        "approved": False,
        "signal": "HOLD",
        "score": round(buy_score, 2),
        "threshold": threshold,
        "sl_pct": None,
        "tp_pct": None,
        "reasoning": f"Tidak ada konsensus 2/2 (skor BUY={buy_score:.2f}, butuh {threshold})",
        "models": buy_models,
    }


def run_consensus_with_approver(proposals, symbol, df, ticker, balance_usdt, hold_streak=0, open_position=None):
    """
    Jalankan consensus 2 proposer, lalu kalau lolos → Claude approver.
    df: candle mentah — approver dapat konteks pasar yang sama dgn proposer
        biar bisa analisis independen (bukan cuma setuju/tidak).
    Return (final_decision, approval_info).
    """
    cons = calculate_consensus(proposals, hold_streak)
    if not cons["approved"]:
        return cons, None

    # 2/2 sepakat (atau 1 BUY kuat saat hold-streak) → minta approval Claude
    from src.core import llm_client
    approval = llm_client.get_approval(
        symbol, df, ticker, balance_usdt,
        proposals.get("OpenAI", {}), proposals.get("Gemini", {}),
        open_position,
    )
    if not approval or not approval.get("approved"):
        cons["approved"] = False
        cons["signal"] = "HOLD"
        cons["reasoning"] = f"Claude approver menolak: {approval.get('reasoning', '') if approval else 'no response'}"
        return cons, approval

    # Claude approve — bisa koreksi SL/TP
    if approval.get("sl_pct") is not None:
        cons["sl_pct"] = float(approval["sl_pct"])
    if approval.get("tp_pct") is not None:
        cons["tp_pct"] = float(approval["tp_pct"])
    cons["reasoning"] = f"Approved by Claude: {approval.get('reasoning', '')}"
    return cons, approval
