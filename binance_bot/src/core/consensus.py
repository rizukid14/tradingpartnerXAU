"""
Consensus 2 proposer + 1 approver.

1. GPT + Gemini vote paralel (BUY/HOLD karena spot).
2. Kalau 2/2 sepakat BUY & skor confidence >= threshold → panggil Claude approver.
3. Claude approve → signal eksekusi. Reject / beda pendapat → HOLD.
"""
import logging

import config

log = logging.getLogger("binance_bot")


def calculate_consensus(proposals):
    """
    proposals: dict dari get_proposals() → {model: {signal, confidence, sl_pct, tp_pct, reasoning}}
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
    # Butuh 2/2 sepakat BUY + skor >= threshold
    if len(buy_models) >= 2 and buy_score >= threshold:
        # SL/TP: pakai rata-rata proposal (Claude bisa koreksi nanti)
        sl_pct = sum(sl_pcts) / len(sl_pcts) if sl_pcts else config.DEFAULT_SL_PCT
        tp_pct = sum(tp_pcts) / len(tp_pcts) if tp_pcts else config.DEFAULT_TP_PCT
        return {
            "approved": True,
            "signal": "BUY",
            "score": round(buy_score, 2),
            "threshold": threshold,
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "reasoning": f"2/2 proposer sepakat BUY (skor {buy_score:.2f})",
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


def run_consensus_with_approver(proposals, symbol, ticker, balance_usdt):
    """
    Jalankan consensus 2 proposer, lalu kalau lolos → Claude approver.
    Return (final_decision, approval_info).
    """
    cons = calculate_consensus(proposals)
    if not cons["approved"]:
        return cons, None

    # 2/2 sepakat → minta approval Claude
    from src.core import llm_client
    approval = llm_client.get_approval(
        symbol, ticker, balance_usdt,
        proposals.get("OpenAI", {}), proposals.get("Gemini", {}),
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
