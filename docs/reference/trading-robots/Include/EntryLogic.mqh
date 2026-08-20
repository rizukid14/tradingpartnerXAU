//+------------------------------------------------------------------+
//|                                                   EntryLogic.mqh |
//|                     False Break Detection Trigger Module          |
//+------------------------------------------------------------------+
#ifndef __GOLDSD_ENTRYLOGIC_MQH__
#define __GOLDSD_ENTRYLOGIC_MQH__

#include "Structures.mqh"
#include "ZoneManager.mqh"
#include "LiquidityPool.mqh"

//+------------------------------------------------------------------+
//| CEntryLogic - Evaluates entry conditions for False Break         |
//+------------------------------------------------------------------+
class CEntryLogic
{
private:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;
   bool              m_useSnD;
   
   // Parameters
   double            m_fbMinPips;       // 5.0 pips
   double            m_fbWickBodyRatio; // 2.0
   int               m_fbMaxCandles;    // 2 candles
   
public:
   CEntryLogic() {}

   bool Init(string symbol, ENUM_TIMEFRAMES tf, double fbMinPips, double fbWickBodyRatio, int fbMaxCandles, bool useSnD)
   {
      m_symbol = symbol;
      m_tf = tf;
      m_fbMinPips = fbMinPips;
      m_fbWickBodyRatio = fbWickBodyRatio;
      m_fbMaxCandles = fbMaxCandles;
      m_useSnD = useSnD;
      return true;
   }

   //--- Scan for signals (OR Logic: SnD+Trend OR FalseBreak+Trend)
   bool CheckSignal(CZoneManager &_zm, CLiquidityPool &_lp, SEntrySignal &signal)
   {
      signal.Reset();
      
      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      if(CopyRates(m_symbol, m_tf, 0, 5, rates) < 5) return false;
      
      double atr = _zm.GetATRValue(1);
      if(atr <= 0) return false;

      // 1. Check for FALSE BREAK (Stage B) - Highest Priority
      SLiquidityPool pools[];
      int poolCount = _lp.GetActivePools(pools);
      for(int p=0; p<poolCount; p++)
      {
         if(pools[p].isHighPool) {
            if(EvaluateFalseBreak(rates, pools[p].level, true, signal)) {
               signal.direction = ORDER_TYPE_SELL;
               signal.reason = "LP Sweep";
               return true;
            }
         } else {
            if(EvaluateFalseBreak(rates, pools[p].level, false, signal)) {
               signal.direction = ORDER_TYPE_BUY;
               signal.reason = "LP Sweep";
               return true;
            }
         }
      }

      // 2. Check for SnD ZONE RETEST (Stage A) - Secondary Priority
      if(m_useSnD)
      {
         SZone zones[];
         int zoneCount = _zm.GetValidZones(zones);
         for(int z=0; z<zoneCount; z++)
         {
            // Is price inside zone?
            double price = (zones[z].type == ZONE_SUPPLY) ? SymbolInfoDouble(m_symbol, SYMBOL_BID) : SymbolInfoDouble(m_symbol, SYMBOL_ASK);
            if(price >= zones[z].lower && price <= zones[z].upper)
            {
               // We need some rejection inside the zone (Pin Bar)
               if(EvaluateSnDRejection(rates, zones[z], signal))
               {
                  signal.direction = (zones[z].type == ZONE_SUPPLY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
                  signal.reason = "SnD Retest";
                  return true;
               }
            }
         }
      }

      return false;
   }

private:
   //--- Specific rejection check for SnD zones without requiring a pool sweep
   bool EvaluateSnDRejection(const MqlRates &rates[], SZone &zone, SEntrySignal &signal)
   {
      int i = 1; 
      double body = MathAbs(rates[i].close - rates[i].open);
      double upperWick = rates[i].high - MathMax(rates[i].close, rates[i].open);
      double lowerWick = MathMin(rates[i].close, rates[i].open) - rates[i].low;
      if(body == 0) body = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

      if(zone.type == ZONE_SUPPLY)
      {
         if(upperWick >= m_fbWickBodyRatio * body)
         {
            signal.valid = true;
            signal.signalTime = TimeCurrent();
            signal.entryPrice = SymbolInfoDouble(m_symbol, SYMBOL_BID);
            signal.slPrice = rates[i].high;
            return true;
         }
      }
      else if(zone.type == ZONE_DEMAND)
      {
         if(lowerWick >= m_fbWickBodyRatio * body)
         {
            signal.valid = true;
            signal.signalTime = TimeCurrent();
            signal.entryPrice = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
            signal.slPrice = rates[i].low;
            return true;
         }
      }
      return false;
   }

   bool EvaluateFalseBreak(const MqlRates &rates[], double poolLevel, bool isHighPool, SEntrySignal &signal)
   {
      double minPenetration = CPipUtil::PipToPrice(m_symbol, m_fbMinPips);
      for(int i=1; i<=m_fbMaxCandles; i++)
      {
         bool penetrated = false;
         if(isHighPool) penetrated = (rates[i].high >= poolLevel + minPenetration);
         else           penetrated = (rates[i].low <= poolLevel - minPenetration);
         
         if(!penetrated) continue;
         
         bool closedInside = false;
         if(isHighPool) closedInside = (rates[i].close < poolLevel);
         else           closedInside = (rates[i].close > poolLevel);
         
         if(!closedInside) continue;
         
         double body = MathAbs(rates[i].close - rates[i].open);
         double upperWick = rates[i].high - MathMax(rates[i].close, rates[i].open);
         double lowerWick = MathMin(rates[i].close, rates[i].open) - rates[i].low;
         
         if(body == 0) body = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
         
         if(isHighPool)
         {
            if(upperWick < m_fbWickBodyRatio * body) continue;
         }
         else
         {
            if(lowerWick < m_fbWickBodyRatio * body) continue;
         }
         
         signal.valid = true;
         signal.signalTime = TimeCurrent();
         signal.entryPrice = (isHighPool) ? SymbolInfoDouble(m_symbol, SYMBOL_BID) : SymbolInfoDouble(m_symbol, SYMBOL_ASK);
         
         if(isHighPool) signal.slPrice = rates[i].high;
         else           signal.slPrice = rates[i].low;
         
         return true;
      }
      return false;
   }
};

#endif
