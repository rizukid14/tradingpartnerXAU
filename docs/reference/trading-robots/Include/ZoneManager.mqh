//+------------------------------------------------------------------+
//|                                                 ZoneManager.mqh  |
//|             Supply & Demand Zone Engine + HTF Bias Module         |
//+------------------------------------------------------------------+
#ifndef __GOLDSD_ZONEMANAGER_MQH__
#define __GOLDSD_ZONEMANAGER_MQH__

#include "Structures.mqh"

//+------------------------------------------------------------------+
//| CZoneManager - Detects SnD zones and determines HTF bias         |
//+------------------------------------------------------------------+
class CZoneManager
{
private:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;           
   int               m_atrHandle;    
   int               m_emaH1Handle;  
   int               m_emaH4Handle;  
   
   double            m_impulseATRMult;  
   double            m_baseMaxATRMult;  
   int               m_baseMaxCandles;  
   int               m_zoneMaxAge;      
   
   SZone             m_zones[];
   int               m_zoneCount;
   int               m_maxZones;
   ENUM_HTF_BIAS     m_currentBias;
   int               m_zoneIdCounter;

   // Helper: Check if zone is still fresh (private internal logic)
   bool IsZoneFresh(const SZone &zone)
   {
      int count = iBarShift(m_symbol, m_tf, zone.birthTime);
      if(count < 1) return true;
      
      MqlRates rates[];
      if(CopyRates(m_symbol, m_tf, 1, count, rates) < count) return true;
      
      for(int i=0; i<count; i++)
      {
         if(rates[i].close <= zone.upper && rates[i].close >= zone.lower) return false;
      }
      return true;
   }

public:
   // Constructor
   CZoneManager() : m_zoneCount(0), m_maxZones(100),
      m_zoneIdCounter(0), m_currentBias(BIAS_NEUTRAL),
      m_atrHandle(INVALID_HANDLE), m_emaH4Handle(INVALID_HANDLE),
      m_emaH1Handle(INVALID_HANDLE) {}
   
   // Destructor
   ~CZoneManager() { Deinit(); }

   // Public: Get ATR value (needed by EntryLogic and RiskManager)
   double GetATRValue(int shift)
   {
      double buf[1];
      if(CopyBuffer(m_atrHandle, 0, shift, 1, buf) < 1) 
      {
         return SymbolInfoDouble(m_symbol, SYMBOL_POINT) * 100; // Fallback
      }
      return buf[0];
   }

   // Initialize indicators
   bool Init(string symbol, ENUM_TIMEFRAMES tf,
             double impulseATRMult, double baseMaxATRMult,
             int baseMaxCandles, int zoneMaxAge)
   {
      m_symbol=symbol;
      m_tf=tf;
      m_impulseATRMult=impulseATRMult;
      m_baseMaxATRMult=baseMaxATRMult;
      m_baseMaxCandles=baseMaxCandles;
      m_zoneMaxAge=zoneMaxAge;
      
      ArrayResize(m_zones, m_maxZones);
      
      m_atrHandle=iATR(m_symbol,m_tf,14);
      m_emaH1Handle = iMA(m_symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
      m_emaH4Handle = iMA(m_symbol, PERIOD_H4, 50, 0, MODE_EMA, PRICE_CLOSE);
      
      return(m_atrHandle != INVALID_HANDLE && m_emaH1Handle != INVALID_HANDLE && m_emaH4Handle != INVALID_HANDLE);
   }
   
   void Deinit()
   {
      if(m_atrHandle!=INVALID_HANDLE) IndicatorRelease(m_atrHandle);
      if(m_emaH4Handle!=INVALID_HANDLE) IndicatorRelease(m_emaH4Handle);
      if(m_emaH1Handle!=INVALID_HANDLE) IndicatorRelease(m_emaH1Handle);
      CleanChartObjects();
   }
   
   // Update bias (EMA alignment on H1 & H4)
   void UpdateBias()
   {
      double emaH1[1], emaH4[1], closeH1[1], closeH4[1];
      if(CopyBuffer(m_emaH1Handle,0,0,1,emaH1)<1 || CopyBuffer(m_emaH4Handle,0,0,1,emaH4)<1) return;
      if(CopyClose(m_symbol,PERIOD_H1,0,1,closeH1)<1 || CopyClose(m_symbol,PERIOD_H4,0,1,closeH4)<1) return;
      
      bool h1Bull = (closeH1[0] > emaH1[0]);
      bool h4Bull = (closeH4[0] > emaH4[0]);
      
      if(h1Bull && h4Bull) m_currentBias = BIAS_BULLISH;
      else if(!h1Bull && !h4Bull) m_currentBias = BIAS_BEARISH;
      else m_currentBias = BIAS_NEUTRAL;
   }
   
   ENUM_HTF_BIAS GetBias() const { return m_currentBias; }

   // Main zone detection logic
   void RefreshZones()
   {
      MqlRates rates[];
      double atr = GetATRValue(1);
      
      if(atr <= 0) {
         Print("GSnD Debug: ATR not ready yet.");
         return;
      }

      int copied = CopyRates(m_symbol, m_tf, 0, m_zoneMaxAge + 50, rates);
      if(copied < 10) {
         Print("GSnD Debug: Failed to copy rates. Copied: ", copied);
         return;
      }
      
      ArraySetAsSeries(rates, true);
      
      // 1. Expire old zones
      for(int z=0; z<m_zoneCount; z++)
      {
         if(!m_zones[z].active) continue;
         int barsAgo = iBarShift(m_symbol, m_tf, m_zones[z].birthTime);
         if(barsAgo > m_zoneMaxAge || barsAgo < 0) m_zones[z].active = false;
      }
      
      int newZonesThisScan = 0;
      
      // 2. Scan for new zones
      for(int i=1; i < (copied - m_baseMaxCandles - 1); i++)
      {
         double body = MathAbs(rates[i].close - rates[i].open);
         // Lowering threshold to 1.2x ATR for higher sensitivity
         if(body < (m_impulseATRMult * 0.8) * atr) continue;
         
         // Found potential impulse
         bool isBull = (rates[i].close > rates[i].open);
         double baseHigh = 0;
         double baseLow = DBL_MAX;
         int baseCandlesFound = 0;
         
         for(int b = i + 1; b <= i + m_baseMaxCandles && b < copied; b++)
         {
            double bBody = MathAbs(rates[b].close - rates[b].open);
            if(bBody > 0.85 * atr) break; // Relaxed base slightly more
            
            if(rates[b].high > baseHigh) baseHigh = rates[b].high;
            if(rates[b].low < baseLow) baseLow = rates[b].low;
            baseCandlesFound++;
         }
         
         if(baseCandlesFound == 0) continue;
         
         if((baseHigh - baseLow) > m_baseMaxATRMult * atr) continue;
         
         bool dup = false;
         for(int z=0; z < m_zoneCount; z++)
         {
            if(m_zones[z].birthTime == rates[i].time) { dup = true; break; }
         }
         
         if(!dup)
         {
            SZone newZone;
            newZone.type = isBull ? ZONE_DEMAND : ZONE_SUPPLY;
            newZone.upper = baseHigh;
            newZone.lower = baseLow;
            newZone.birthTime = rates[i].time;
            newZone.active = true;
            newZone.fresh = true;
            newZone.id = StringFormat("%d", ++m_zoneIdCounter);
            
            if(IsZoneFresh(newZone)) {
               AddZone(newZone);
               newZonesThisScan++;
            }
         }
      }
      
      if(newZonesThisScan > 0) Print("GSnD Debug: Detected ", newZonesThisScan, " new zones.");
      DrawZones();
   }

   void UpdateFreshness()
   {
      for(int z=0; z<m_zoneCount; z++)
         if(m_zones[z].active && m_zones[z].fresh && !IsZoneFresh(m_zones[z])) m_zones[z].fresh = false;
   }

   int GetValidZones(SZone &outZones[])
   {
      int count = 0;
      ArrayResize(outZones, m_zoneCount);
      for(int z=0; z<m_zoneCount; z++)
         if(m_zones[z].active && m_zones[z].fresh) outZones[count++] = m_zones[z];
      ArrayResize(outZones, count);
      return count;
   }
   
   int GetValidZoneCount() { SZone tmp[]; return GetValidZones(tmp); }
   int GetDemandCount() { int c=0; for(int i=0; i<m_zoneCount; i++) if(m_zones[i].active && m_zones[i].fresh && m_zones[i].type==ZONE_DEMAND) c++; return c; }
   int GetSupplyCount() { int c=0; for(int i=0; i<m_zoneCount; i++) if(m_zones[i].active && m_zones[i].fresh && m_zones[i].type==ZONE_SUPPLY) c++; return c; }

   bool FindNearestZoneForTP(ENUM_ORDER_TYPE dir, double entryPrice, double &outLevel)
   {
      double minDist = DBL_MAX; bool found = false;
      for(int z=0; z<m_zoneCount; z++)
      {
         if(!m_zones[z].active) continue;
         if(dir == ORDER_TYPE_BUY && m_zones[z].type == ZONE_SUPPLY && m_zones[z].lower > entryPrice)
         {
            double d = m_zones[z].lower - entryPrice;
            if(d < minDist) { minDist = d; outLevel = m_zones[z].lower; found = true; }
         }
         else if(dir == ORDER_TYPE_SELL && m_zones[z].type == ZONE_DEMAND && m_zones[z].upper < entryPrice)
         {
            double d = entryPrice - m_zones[z].upper;
            if(d < minDist) { minDist = d; outLevel = m_zones[z].upper; found = true; }
         }
      }
      return found;
   }

private:
   void AddZone(const SZone &zone)
   {
      if(m_zoneCount >= m_maxZones) { for(int i=0; i<m_maxZones-1; i++) m_zones[i] = m_zones[i+1]; m_zones[m_maxZones-1] = zone; }
      else m_zones[m_zoneCount++] = zone;
   }

   void DrawZones()
   {
      // We don't clean all every time, just the ones we are about to redraw
      // Actually, CleanChartObjects handles the prefix GSnD_Zone_
      CleanChartObjects();
      
      for(int z=0; z<m_zoneCount; z++)
      {
         if(!m_zones[z].active) continue;
         
         string name = "GSnD_Zone_" + m_zones[z].id;
         // Rectangle from birth time to current time
         ObjectCreate(0, name, OBJ_RECTANGLE, 0, m_zones[z].birthTime, m_zones[z].upper, TimeCurrent(), m_zones[z].lower);
         
         color zoneColor;
         if(m_zones[z].type == ZONE_SUPPLY)
            zoneColor = m_zones[z].fresh ? clrRed : C'40,0,0'; // Faint red if not fresh
         else
            zoneColor = m_zones[z].fresh ? clrBlue : C'0,0,40'; // Faint blue if not fresh
            
         ObjectSetInteger(0, name, OBJPROP_COLOR, zoneColor);
         ObjectSetInteger(0, name, OBJPROP_FILL, true);
         ObjectSetInteger(0, name, OBJPROP_BACK, true);
         ObjectSetInteger(0, name, OBJPROP_STYLE, m_zones[z].fresh ? STYLE_SOLID : STYLE_DOT);
      }
   }

   void CleanChartObjects() { ObjectsDeleteAll(0, "GSnD_Zone_"); }
};

#endif
