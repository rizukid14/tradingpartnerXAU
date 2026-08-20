//+------------------------------------------------------------------+
//|                                               LiquidityPool.mqh  |
//|                    Equal Highs & Lows Scanner Module             |
//+------------------------------------------------------------------+
#ifndef __GOLDSD_LIQUIDITYPOOL_MQH__
#define __GOLDSD_LIQUIDITYPOOL_MQH__

#include "Structures.mqh"

//+------------------------------------------------------------------+
//| CLiquidityPool - Scans for clusters of equal highs/lows           |
//+------------------------------------------------------------------+
class CLiquidityPool
{
private:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;
   
   // Parameters
   double            m_equalTolPips;  // 5.0 pips default
   int               m_scanBars;      // 50 bars default
   int               m_minTouches;    // 2 touches default
   
   // Pool storage
   SLiquidityPool    m_pools[];
   int               m_poolCount;
   int               m_maxPools;
   int               m_poolIdCounter;

   // Helper to check if a bar is a swing high
   bool IsSwingHigh(const MqlRates &rates[], int i)
   {
      if(i < 1 || i >= ArraySize(rates)-1) return false;
      return (rates[i].high > rates[i-1].high && rates[i].high > rates[i+1].high);
   }

   // Helper to check if a bar is a swing low
   bool IsSwingLow(const MqlRates &rates[], int i)
   {
      if(i < 1 || i >= ArraySize(rates)-1) return false;
      return (rates[i].low < rates[i-1].low && rates[i].low < rates[i+1].low);
   }

public:
   CLiquidityPool() : m_poolCount(0), m_maxPools(50), m_poolIdCounter(0) {}

   bool Init(string symbol, ENUM_TIMEFRAMES tf, double tolPips, int scanBars, int minTouches)
   {
      m_symbol = symbol;
      m_tf = tf;
      m_equalTolPips = tolPips;
      m_scanBars = scanBars;
      m_minTouches = minTouches;
      
      ArrayResize(m_pools, m_maxPools);
      return true;
   }

   void Deinit()
   {
      CleanChartObjects();
   }

   //--- Full scan and rebuild of liquidity pools (called on timer)
   void ScanPools()
   {
      m_poolCount = 0;
      double tolPrice = CPipUtil::PipToPrice(m_symbol, m_equalTolPips);
      
      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      if(CopyRates(m_symbol, m_tf, 0, m_scanBars + 2, rates) < m_scanBars + 2) return;

      // 1. Collect swing points
      double highs[]; int highBars[];
      double lows[]; int lowBars[];
      int hCount=0, lCount=0;
      ArrayResize(highs, m_scanBars); ArrayResize(highBars, m_scanBars);
      ArrayResize(lows, m_scanBars); ArrayResize(lowBars, m_scanBars);

      for(int i=1; i<=m_scanBars; i++)
      {
         if(IsSwingHigh(rates, i)) { highs[hCount]=rates[i].high; highBars[hCount]=i; hCount++; }
         if(IsSwingLow(rates, i))  { lows[lCount]=rates[i].low;   lowBars[lCount]=i;  lCount++; }
      }

      // 2. Group Equal Highs
      bool usedHigh[100]; ArrayInitialize(usedHigh, false);
      for(int i=0; i<hCount; i++)
      {
         if(usedHigh[i]) continue;
         SLiquidityPool pool;
         pool.Reset();
         pool.level = highs[i];
         pool.touchCount = 1;
         pool.isHighPool = true;
         pool.firstTouch = rates[highBars[i]].time;
         pool.lastTouch = rates[highBars[i]].time;
         usedHigh[i] = true;

         for(int j=i+1; j<hCount; j++)
         {
            if(MathAbs(highs[j] - pool.level) <= tolPrice)
            {
               pool.touchCount++;
               pool.level = (pool.level + highs[j]) / 2.0; // Average level
               if(rates[highBars[j]].time < pool.firstTouch) pool.firstTouch = rates[highBars[j]].time;
               if(rates[highBars[j]].time > pool.lastTouch) pool.lastTouch = rates[highBars[j]].time;
               usedHigh[j] = true;
            }
         }

         if(pool.touchCount >= m_minTouches)
         {
            AddPool(pool);
         }
      }

      // 3. Group Equal Lows
      bool usedLow[100]; ArrayInitialize(usedLow, false);
      for(int i=0; i<lCount; i++)
      {
         if(usedLow[i]) continue;
         SLiquidityPool pool;
         pool.Reset();
         pool.level = lows[i];
         pool.touchCount = 1;
         pool.isHighPool = false;
         pool.firstTouch = rates[lowBars[i]].time;
         pool.lastTouch = rates[lowBars[i]].time;
         usedLow[i] = true;

         for(int j=i+1; j<lCount; j++)
         {
            if(MathAbs(lows[j] - pool.level) <= tolPrice)
            {
               pool.touchCount++;
               pool.level = (pool.level + lows[j]) / 2.0;
               if(rates[lowBars[j]].time < pool.firstTouch) pool.firstTouch = rates[lowBars[j]].time;
               if(rates[lowBars[j]].time > pool.lastTouch) pool.lastTouch = rates[lowBars[j]].time;
               usedLow[j] = true;
            }
         }

         if(pool.touchCount >= m_minTouches)
         {
            AddPool(pool);
         }
      }

      // 4. Check for Swept status (candle close beyond)
      UpdateSweptStatus(rates);
      DrawPools();
   }

   void AddPool(SLiquidityPool &pool)
   {
      if(m_poolCount >= m_maxPools) return;
      pool.id = StringFormat("GSnD_LP%d", m_poolIdCounter++);
      m_pools[m_poolCount++] = pool;
   }

   void UpdateSweptStatus(const MqlRates &rates[])
   {
      for(int p=0; p<m_poolCount; p++)
      {
         if(m_pools[p].swept) continue;
         // Scan bars from pool formation to now
         int startBar = iBarShift(m_symbol, m_tf, m_pools[p].lastTouch);
         for(int i=startBar-1; i>=0; i--)
         {
            if(m_pools[p].isHighPool)
            {
               if(rates[i].close > m_pools[p].level) { m_pools[p].swept = true; break; }
            }
            else
            {
               if(rates[i].close < m_pools[p].level) { m_pools[p].swept = true; break; }
            }
         }
      }
   }

   //--- Get all unswept pools
   int GetActivePools(SLiquidityPool &outPools[])
   {
      int count = 0;
      ArrayResize(outPools, m_poolCount);
      for(int p=0; p<m_poolCount; p++)
      {
         if(!m_pools[p].swept) outPools[count++] = m_pools[p];
      }
      ArrayResize(outPools, count);
      return count;
   }

   //--- Get unswept pools near a zone (within 1x ATR)
   int GetPoolsNearZone(const SZone &zone, double atr, SLiquidityPool &outPools[])
   {
      int count = 0;
      ArrayResize(outPools, m_poolCount);
      for(int p=0; p<m_poolCount; p++)
      {
         if(m_pools[p].swept) continue;
         
         // Proximity check: pool level near zone boundary
         bool near = false;
         if(zone.type == ZONE_SUPPLY && m_pools[p].isHighPool)
         {
            if(MathAbs(m_pools[p].level - zone.upper) <= atr * 3.0 || MathAbs(m_pools[p].level - zone.lower) <= atr * 3.0)
               near = true;
         }
         else if(zone.type == ZONE_DEMAND && !m_pools[p].isHighPool)
         {
            if(MathAbs(m_pools[p].level - zone.upper) <= atr * 3.0 || MathAbs(m_pools[p].level - zone.lower) <= atr * 3.0)
               near = true;
         }

         if(near) outPools[count++] = m_pools[p];
      }
      ArrayResize(outPools, count);
      return count;
   }

   int GetActivePoolCount()
   {
      int c=0;
      for(int p=0; p<m_poolCount; p++) if(!m_pools[p].swept) c++;
      return c;
   }

   void DrawPools()
   {
      CleanChartObjects();
      for(int p=0; p<m_poolCount; p++)
      {
         if(m_pools[p].swept) continue;
         
         color pColor = m_pools[p].isHighPool ? clrOrangeRed : clrLimeGreen;
         ObjectCreate(0, m_pools[p].id, OBJ_HLINE, 0, 0, m_pools[p].level);
         ObjectSetInteger(0, m_pools[p].id, OBJPROP_COLOR, pColor);
         ObjectSetInteger(0, m_pools[p].id, OBJPROP_STYLE, STYLE_DOT);
         ObjectSetInteger(0, m_pools[p].id, OBJPROP_WIDTH, 1);
         ObjectSetString(0, m_pools[p].id, OBJPROP_TOOLTIP, 
            StringFormat("Liquidity Pool | Touches: %d", m_pools[p].touchCount));
      }
      ChartRedraw(0);
   }

   void CleanChartObjects()
   {
      int total = ObjectsTotal(0);
      for(int i=total-1; i>=0; i--)
      {
         string name = ObjectName(0, i);
         if(StringFind(name, "GSnD_LP") >= 0) ObjectDelete(0, name);
      }
   }
};

#endif
