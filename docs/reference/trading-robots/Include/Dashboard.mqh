//+------------------------------------------------------------------+
//|                                                   Dashboard.mqh  |
//|                    On-Chart Information Panel Module             |
//+------------------------------------------------------------------+
#ifndef __GOLDSD_DASHBOARD_MQH__
#define __GOLDSD_DASHBOARD_MQH__

#include "Structures.mqh"
#include "ZoneManager.mqh"
#include "LiquidityPool.mqh"
#include "RiskManager.mqh"
#include "NewsFilter.mqh"

//+------------------------------------------------------------------+
//| CDashboard - Renders EA status and metrics on the chart          |
//+------------------------------------------------------------------+
class CDashboard
{
private:
   string m_prefix;
   int    m_x, m_y;
   int    m_rowHeight;

   void CreateLabel(string name, string text, int x, int y, color clr, int fontSize)
   {
      string objName = m_prefix + name;
      if(ObjectFind(0, objName) < 0)
         ObjectCreate(0, objName, OBJ_LABEL, 0, 0, 0);
         
      ObjectSetInteger(0, objName, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, objName, OBJPROP_YDISTANCE, y);
      ObjectSetInteger(0, objName, OBJPROP_COLOR, clr);
      ObjectSetInteger(0, objName, OBJPROP_FONTSIZE, fontSize);
      ObjectSetString(0, objName, OBJPROP_TEXT, text);
      ObjectSetInteger(0, objName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, objName, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, objName, OBJPROP_HIDDEN, true);
   }

public:
   CDashboard() : m_prefix("GSnD_Dash_"), m_x(20), m_y(20), m_rowHeight(18) {}

   void Init()
   {
      string bgName = m_prefix + "BG";
      if(ObjectFind(0, bgName) < 0)
         ObjectCreate(0, bgName, OBJ_RECTANGLE_LABEL, 0, 0, 0);
         
      ObjectSetInteger(0, bgName, OBJPROP_XDISTANCE, m_x - 10);
      ObjectSetInteger(0, bgName, OBJPROP_YDISTANCE, m_y - 10);
      ObjectSetInteger(0, bgName, OBJPROP_XSIZE, 220);
      ObjectSetInteger(0, bgName, OBJPROP_YSIZE, 260);
      ObjectSetInteger(0, bgName, OBJPROP_BGCOLOR, clrBlack);
      ObjectSetInteger(0, bgName, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, bgName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, bgName, OBJPROP_BACK, false);
      ObjectSetInteger(0, bgName, OBJPROP_COLOR, clrGray);
   }

   void Deinit()
   {
      ObjectsDeleteAll(0, m_prefix);
   }

   void Update(CZoneManager &_zm, CLiquidityPool &_lp, CRiskManager &_rm, CNewsFilter &_nf, SEntrySignal &_lastSignal)
   {
      int curY = m_y;
      
      CreateLabel("Title", "🤖 GoldSnD EA v1.0", m_x, curY, clrGold, 10);
      curY += m_rowHeight + 5;
      
      ENUM_HTF_BIAS bias = _zm.GetBias();
      string biasT = (bias == BIAS_BULLISH) ? "BULLISH" : (bias == BIAS_BEARISH ? "BEARISH" : "NEUTRAL");
      color biasC = (bias == BIAS_BULLISH) ? clrLime : (bias == BIAS_BEARISH ? clrRed : clrLightGray);
      CreateLabel("Bias", "HTF Bias: " + biasT, m_x, curY, biasC, 9);
      curY += m_rowHeight;
      
      CreateLabel("Zones", StringFormat("Active Zones: %d (D:%d/S:%d)", _zm.GetValidZoneCount(), _zm.GetDemandCount(), _zm.GetSupplyCount()), m_x, curY, clrWhite, 9);
      curY += m_rowHeight;
      CreateLabel("Pools", StringFormat("Liq. Pools: %d unswept", _lp.GetActivePoolCount()), m_x, curY, clrWhite, 9);
      curY += m_rowHeight + 5;
      
      string sigT = _lastSignal.valid ? StringFormat("%s @ %.2f", (_lastSignal.direction == ORDER_TYPE_BUY ? "BUY" : "SELL"), _lastSignal.entryPrice) : "None";
      CreateLabel("Signal", "Last Signal: " + sigT, m_x, curY, _lastSignal.valid ? clrCyan : clrGray, 9);
      curY += m_rowHeight + 5;
      
      double pnl = _rm.GetDailyLossPct();
      CreateLabel("PNL", StringFormat("Today P&L: %.2f%%", -pnl), m_x, curY, pnl >= _rm.GetMaxDailyLoss() ? clrRed : clrWhite, 9);
      curY += m_rowHeight;
      CreateLabel("Status", _rm.IsTradingAllowed() ? "Status: ● TRADING" : "Status: ⛔ PAUSED", m_x, curY, _rm.IsTradingAllowed() ? clrLime : clrRed, 9);
      curY += m_rowHeight + 5;
      
      datetime nTime = _nf.GetNextEventTime();
      CreateLabel("News", "Next News: " + (nTime > 0 ? _nf.GetNextEventName() : "None"), m_x, curY, clrWhite, 9);
      curY += m_rowHeight;
      
      string countD = "Countdown: ";
      if(nTime > 0) {
         int sec = (int)(nTime - TimeCurrent());
         if(sec > 0) countD += StringFormat("%02d:%02d", sec/3600, (sec%3600)/60);
         else countD += "Now";
      } else countD += "N/A";
      CreateLabel("Countdown", countD, m_x, curY, clrLightGray, 9);
      curY += m_rowHeight;
      
      CreateLabel("Blackout", "News Block: " + (_nf.IsBlackoutActive() ? "● ACTIVE" : "CLEAR"), m_x, curY, _nf.IsBlackoutActive() ? clrRed : clrLime, 9);
      
      ChartRedraw(0);
   }
};

#endif
