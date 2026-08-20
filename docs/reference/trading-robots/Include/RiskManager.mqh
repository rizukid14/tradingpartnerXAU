//+------------------------------------------------------------------+
//|                                                  RiskManager.mqh |
//|          Risk Management, Sizing, SL/TP & Trailing Module        |
//+------------------------------------------------------------------+
#ifndef __GOLDSD_RISKMANAGER_MQH__
#define __GOLDSD_RISKMANAGER_MQH__

#include <Trade\Trade.mqh>
#include "Structures.mqh"
#include "ZoneManager.mqh"

//+------------------------------------------------------------------+
//| CRiskManager - Handles risk calculation and trade management     |
//+------------------------------------------------------------------+
class CRiskManager
{
private:
   CTrade            m_trade;
   string            m_symbol;
   long              m_magic;
   
   // Parameters
   double            m_riskPercent;     // 1.5%
   double            m_maxDailyLoss;    // 5.0%
   int               m_maxTrades;       // 2
   double            m_slBufferATR;     // 0.5
   double            m_tp1RR;           // 1.5
   double            m_tp2MinRR;        // 2.0
   double            m_tp3RR;           // 3.0
   double            m_tp1ClosePct;     // 50.0%
   double            m_trailATRMult;    // 1.0
   double            m_beProfitPips;    // 50.0
   double            m_beLockPips;      // 2.0
   double            m_dailyTargetPct;  // 3.0%
   bool              m_useCompound;     // true
   
   // Tracking
   double            m_dailyStartEquity;
   datetime          m_lastDailyReset;
   bool              m_circuitBroken;
   bool              m_targetReached;

public:
   CRiskManager() : m_circuitBroken(false), m_targetReached(false) 
   {
      m_lastDailyReset = 0;
   }

   bool Init(string symbol, long magic, double riskPct, double maxDailyLoss, int maxTrades,
             double slBuffer, double tp1RR, double tp2MinRR, double tp3RR, 
             double tp1ClosePct, double trailATR, 
             double bePips, double beLock,
             double dailyTargetPct, bool useCompound)
   {
      m_symbol = symbol;
      m_magic = magic;
      m_riskPercent = riskPct;
      m_maxDailyLoss = maxDailyLoss;
      m_maxTrades = maxTrades;
      m_slBufferATR = slBuffer;
      m_tp1RR = tp1RR;
      m_tp2MinRR = tp2MinRR;
      m_tp3RR = tp3RR;
      m_tp1ClosePct = tp1ClosePct;
      m_trailATRMult = trailATR;
      m_beProfitPips = bePips;
      m_beLockPips = beLock;
      m_dailyTargetPct = dailyTargetPct;
      m_useCompound = useCompound;
      
      m_trade.SetExpertMagicNumber(m_magic);
      m_dailyStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      m_lastDailyReset = iTime(m_symbol, PERIOD_D1, 0);
      return true;
   }
   
   //--- Compound lot calculation
   double GetLotSize(double slDistPoints, SEntrySignal &signal)
   {
      double baseVal = m_useCompound ? AccountInfoDouble(ACCOUNT_EQUITY) : AccountInfoDouble(ACCOUNT_BALANCE);
      double riskAmount = baseVal * (m_riskPercent / 100.0);
      
      double tickValue = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
      double tickSize = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
      
      if(slDistPoints == 0 || tickValue == 0) return 0;
      
      double lot = (riskAmount) / (slDistPoints / tickSize * tickValue);
      
      double minLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
      double maxLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
      double step = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
      
      lot = MathFloor(lot/step)*step;
      if(lot < minLot) lot = minLot;
      if(lot > maxLot) lot = maxLot;
      
      return lot;
   }
   
   //--- Checks if daily profit target or loss limit is hit
   bool IsTradingAllowed()
   {
      ResetDailyIfNeeded();
      
      if(m_circuitBroken || m_targetReached) return false;
      
      double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      double pnl = currentEquity - m_dailyStartEquity;
      double pnlPct = (pnl / m_dailyStartEquity) * 100.0;
      
      // Check Daily Loss
      if(pnlPct <= -m_maxDailyLoss)
      {
         m_circuitBroken = true;
         Print("Daily Loss Limit Hit (", pnlPct, "%). Stopping for today.");
         return false;
      }
      
      // Check Daily Target
      if(m_dailyTargetPct > 0 && pnlPct >= m_dailyTargetPct)
      {
         m_targetReached = true;
         Print("Daily Profit Target Reached (", pnlPct, "%). Locking gains for today!");
         return false;
      }
      
      int count = 0;
      for(int i=PositionsTotal()-1; i>=0; i--)
      {
         if(PositionSelectByTicket(PositionGetTicket(i)))
         {
            if(PositionGetString(POSITION_SYMBOL) == m_symbol && PositionGetInteger(POSITION_MAGIC) == m_magic) count++;
         }
      }
      
      return (count < m_maxTrades);
   }

   void ResetDailyIfNeeded()
   {
      datetime today = iTime(m_symbol, PERIOD_D1, 0);
      if(today != m_lastDailyReset)
      {
         m_dailyStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
         m_lastDailyReset = today;
         m_circuitBroken = false;
         m_targetReached = false;
      }
   }

   //--- Finalize signal with risk parameters
   bool FinalizeSignal(CZoneManager &_zm, SEntrySignal &signal)
   {
      double atr = _zm.GetATRValue(1);
      double buffer = atr * m_slBufferATR;
      
      // 1. Refine SL with buffer
      if(signal.direction == ORDER_TYPE_BUY) signal.slPrice -= buffer;
      else                                   signal.slPrice += buffer;
      
      double riskPoints = MathAbs(signal.entryPrice - signal.slPrice);
      if(riskPoints <= 0) return false;
      
      // 2. Set TPs
      signal.tp1Price = signal.entryPrice + (signal.direction == ORDER_TYPE_BUY ? riskPoints * m_tp1RR : -riskPoints * m_tp1RR);
      signal.tp3Price = signal.entryPrice + (signal.direction == ORDER_TYPE_BUY ? riskPoints * m_tp3RR : -riskPoints * m_tp3RR);
      
      double tp2Zone;
      if(_zm.FindNearestZoneForTP(signal.direction, signal.entryPrice, tp2Zone))
      {
         double tp2Dist = MathAbs(tp2Zone - signal.entryPrice);
         if(tp2Dist >= riskPoints * m_tp2MinRR) signal.tp2Price = tp2Zone;
      }
      
      // 3. Lot sizing
      double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      double riskAmount = equity * (m_riskPercent / 100.0);
      double tickValue = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
      double tickSize = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
      
      if(tickSize == 0 || tickValue == 0) return false;
      
      double lotSize = riskAmount / ( (riskPoints / tickSize) * tickValue );
      
      // Normalize lot size
      double minLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
      double maxLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
      double lotStep = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
      
      lotSize = MathFloor(lotSize / lotStep) * lotStep;
      if(lotSize < minLot) lotSize = minLot;
      if(lotSize > maxLot) lotSize = maxLot;
      
      signal.lotSize = lotSize;
      return true;
   }

   //--- Manage open positions (TP1 partial close & Trailing)
   void ManagePositions(CZoneManager &_zm)
   {
      double atr = _zm.GetATRValue(1);
      
      for(int i=PositionsTotal()-1; i>=0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket <= 0) continue;
         if(!PositionSelectByTicket(ticket)) continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol || PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
         
         double currentPrice = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? SymbolInfoDouble(m_symbol, SYMBOL_BID) : SymbolInfoDouble(m_symbol, SYMBOL_ASK);
         
         string comment = PositionGetString(POSITION_COMMENT);
         bool tp1Hit = (StringFind(comment, "TP1") >= 0);
         
         double entry = PositionGetDouble(POSITION_PRICE_OPEN);
         double sl = PositionGetDouble(POSITION_SL);
         
         // 1. Partial close at TP1
         if(!tp1Hit)
         {
            double risk = MathAbs(entry - sl);
            bool reached = false;
            if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) reached = (currentPrice >= entry + risk * m_tp1RR);
            else reached = (currentPrice <= entry - risk * m_tp1RR);
            
            if(reached)
            {
               double currentVolume = PositionGetDouble(POSITION_VOLUME);
               double closeVolume = currentVolume * (m_tp1ClosePct / 100.0);
               m_trade.PositionClosePartial(ticket, closeVolume);
               continue; 
            }
         }

         // 2. Break Even (SL+)
         if(m_beProfitPips > 0)
         {
            double entry = PositionGetDouble(POSITION_PRICE_OPEN);
            double currentSL = PositionGetDouble(POSITION_SL);
            double diff = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? (currentPrice - entry) : (entry - currentPrice);
            double profitPips = CPipUtil::PriceToPip(m_symbol, diff);
            
            if(profitPips >= m_beProfitPips)
            {
               double beLevel = 0;
               double buffer = CPipUtil::PipToPrice(m_symbol, m_beLockPips);
               
               if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
               {
                  beLevel = entry + buffer;
                  if(currentSL < beLevel) m_trade.PositionModify(ticket, beLevel, PositionGetDouble(POSITION_TP));
               }
               else
               {
                  beLevel = entry - buffer;
                  if(currentSL > beLevel || currentSL == 0) m_trade.PositionModify(ticket, beLevel, PositionGetDouble(POSITION_TP));
               }
            }
         }

         // 3. Trailing Stop (Activated after TP1 hit)
         else
         {
            double newSL = 0;
            if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
            {
               newSL = currentPrice - (atr * m_trailATRMult);
               if(newSL > sl && newSL > entry) m_trade.PositionModify(ticket, newSL, PositionGetDouble(POSITION_TP));
            }
            else
            {
               newSL = currentPrice + (atr * m_trailATRMult);
               if(newSL < sl && newSL < entry) m_trade.PositionModify(ticket, newSL, PositionGetDouble(POSITION_TP));
            }
         }
      }
   }
   
   double GetDailyLossPct()
   {
      double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      return MathMax(0, (m_dailyStartEquity - currentEquity) / m_dailyStartEquity * 100.0);
   }
   
   double GetMaxDailyLoss() { return m_maxDailyLoss; }
};

#endif
