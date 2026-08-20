//+------------------------------------------------------------------+
//|                                                  GoldSnD_EA.mq5  |
//|                    Strategy: SnD + False Break + Liquidity Pool  |
//|                    Target: XAUUSD, M1 (High Frequency Mode)      |
//+------------------------------------------------------------------+
#property copyright "Antigravity AI"
#property link      "https://github.com/antigravity"
#property version   "1.70"
#property strict

//--- Includes
#include <Trade\Trade.mqh>
#include "Structures.mqh"
#include "ZoneManager.mqh"
#include "LiquidityPool.mqh"
#include "EntryLogic.mqh"
#include "RiskManager.mqh"
#include "NewsFilter.mqh"
#include "Dashboard.mqh"

//--- Input Parameters
input group "=== Risk Management ==="
input double   InpRiskPercent     = 1.0;     
input double   InpMaxDailyLoss    = 5.0;     
input int      InpMaxTrades       = 3;       
input double   InpSLBufferATR     = 1.5;     // Extra space for M1 noise
input double   InpTP1_RR          = 1.5;     
input double   InpTP2_MinRR       = 2.0;     
input double   InpTP3_RR          = 3.0;     
input double   InpTP1_ClosePct    = 50.0;    
input double   InpBEProfitPips    = 50.0;    
input double   InpBELockPips      = 2.0;     

input group "=== Zone Detection ==="
input double   InpImpulseATRMult  = 2.0;     
input double   InpBaseMaxATRMult  = 0.6;     
input int      InpBaseMaxCandles  = 8;       
input int      InpZoneMaxAge      = 1200;    

input group "=== Entry Trigger ==="
input double   InpEqualTolPips    = 3.0;     
input int      InpLPScanBars      = 300;     
input int      InpMinLPTouches    = 2;       
input double   InpFBMinPips       = 1.5;     
input double   InpFBWickBodyRatio = 1.5;     // Rejection criteria
input int      InpFBMaxCandles    = 3;       

input group "=== Advanced Filters (100% Growth) ==="
input bool     InpUseSessionFilter= true;    // London/NY only
input int      InpSessionStart    = 14;      
input int      InpSessionEnd      = 22;      
input double   InpDailyTargetPct  = 3.0;     
input bool     InpUseCompoundRisk = true;    

input group "=== Filters & Settings ==="
input bool     InpUseSnDFilter    = true;    
input bool     InpUseBiasFilter   = true;    
input bool     InpUseNewsFilter   = true;    
input int      InpNewsBufferMin   = 60;      
input long     InpMagicNumber     = 20250423;
input string   InpTradeComment    = "GoldSnD_Pro_100";

//--- Global Objects
CZoneManager   ExtZoneManager;
CLiquidityPool ExtLiquidityPool;
CEntryLogic    ExtEntryLogic;
CRiskManager   ExtRiskManager;
CNewsFilter    ExtNewsFilter;
CDashboard     ExtDashboard;
CTrade         trade;
SEntrySignal   lastSignal;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   if(_Symbol != "XAUUSD")
   {
      Alert("This EA is optimized for XAUUSD only.");
   }
   
   if(!ExtZoneManager.Init(_Symbol, _Period, InpImpulseATRMult, InpBaseMaxATRMult, InpBaseMaxCandles, InpZoneMaxAge)) return(INIT_FAILED);
   if(!ExtLiquidityPool.Init(_Symbol, _Period, InpEqualTolPips, InpLPScanBars, InpMinLPTouches)) return(INIT_FAILED);
   if(!ExtEntryLogic.Init(_Symbol, _Period, InpFBMinPips, InpFBWickBodyRatio, InpFBMaxCandles, InpUseSnDFilter)) return(INIT_FAILED);
   if(!ExtRiskManager.Init(_Symbol, InpMagicNumber, InpRiskPercent, InpMaxDailyLoss, InpMaxTrades, InpSLBufferATR, InpTP1_RR, InpTP2_MinRR, InpTP3_RR, InpTP1_ClosePct, 1.0, InpBEProfitPips, InpBELockPips, InpDailyTargetPct, InpUseCompoundRisk)) return(INIT_FAILED);
   ExtNewsFilter.Init(InpNewsBufferMin, InpNewsBufferMin, 15, 15);
   ExtDashboard.Init();
   
   trade.SetExpertMagicNumber(InpMagicNumber);
   lastSignal.Reset();
   
   EventSetTimer(60); 
   OnTimer();
   
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ExtZoneManager.Deinit();
   ExtLiquidityPool.Deinit();
   ExtDashboard.Deinit();
}

void OnTick()
{
   ExtZoneManager.UpdateFreshness();
   ExtRiskManager.ManagePositions(ExtZoneManager);
   
   static datetime lastBar = 0;
   datetime currentBar = iTime(_Symbol, _Period, 0);
   
   if(currentBar != lastBar)
   {
      lastBar = currentBar;
      
      if(!ExtRiskManager.IsTradingAllowed()) return;
      if(InpUseNewsFilter && ExtNewsFilter.IsBlackoutActive()) return;

      if(InpUseSessionFilter)
      {
         MqlDateTime dt;
         TimeCurrent(dt);
         if(dt.hour < InpSessionStart || dt.hour >= InpSessionEnd) return;
      }
      
      ExtZoneManager.UpdateBias();
      ExtZoneManager.RefreshZones();
      ExtLiquidityPool.ScanPools();

      bool biasOk = !InpUseBiasFilter || (ExtZoneManager.GetBias() != BIAS_NEUTRAL);

      if(biasOk)
      {
         if(ExtEntryLogic.CheckSignal(ExtZoneManager, ExtLiquidityPool, lastSignal))
         {
            if(ExtRiskManager.FinalizeSignal(ExtZoneManager, lastSignal))
            {
               string comment = InpTradeComment + " [Z:" + lastSignal.reason + "]";
               if(lastSignal.direction == ORDER_TYPE_BUY)
                  trade.Buy(lastSignal.lotSize, _Symbol, lastSignal.entryPrice, lastSignal.slPrice, lastSignal.tp3Price, comment);
               else
                  trade.Sell(lastSignal.lotSize, _Symbol, lastSignal.entryPrice, lastSignal.slPrice, lastSignal.tp3Price, comment);
            }
         }
      }
   }
   
   ExtDashboard.Update(ExtZoneManager, ExtLiquidityPool, ExtRiskManager, ExtNewsFilter, lastSignal);
}

void OnTimer()
{
   ExtZoneManager.UpdateBias();
   ExtZoneManager.RefreshZones();
   ExtLiquidityPool.ScanPools();
   ExtDashboard.Update(ExtZoneManager, ExtLiquidityPool, ExtRiskManager, ExtNewsFilter, lastSignal);
}
