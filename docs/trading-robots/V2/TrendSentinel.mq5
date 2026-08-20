//+------------------------------------------------------------------+
//|                                              TrendSentinel.mq5   |
//|                                  Copyright 2024, Algorithmic Pro |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2024, Algorithmic Pro"
#property link      "https://www.mql5.com"
#property version   "2.00"
#property strict

//--- Include Trade library
#include <Trade\Trade.mqh>

//--- Input Parameters (Robust Defaults for XAUUSD M1/M5)
input group "Indicator Settings (M1)"
input int      InpFastEMA_M1 = 12;       // Fast EMA M1 (Standard)
input int      InpSlowEMA_M1 = 26;       // Slow EMA M1 (Standard)
input int      InpADXPeriod = 14;        // ADX Period
input int      InpADXThreshold = 22;     // Min ADX (Lebih longgar untuk menangkap awal tren)

input group "Trend Filter (M5 Reference)"
input ENUM_TIMEFRAMES InpTrendTF = PERIOD_M5; 
input int      InpFastEMA_M5 = 20;       
input int      InpSlowEMA_M5 = 50;       

input group "Robust Risk Management (Real Tick Optimized)"
input double   InpRiskPercent = 1.0;     // Risk per trade (%)
input int      InpStopLoss = 50;          // SL (Pips) - Lebih longgar dari OHLC untuk hindari noise
input int      InpTakeProfit = 100;       // TP (Pips) - Target realistis 1:2
input int      InpTrailingStop = 25;      // Trailing (Pips) - Buffer agar tidak gampang tersambar
input int      InpMaxOpenTrades = 1;      
input double   InpMaxDrawdown = 10.0;     

input group "Market Filter"
input int      InpMaxSpread = 40;         // Max spread (Points) - Ketat untuk ECN
input bool     InpOnlyOnBarOpen = true;   // Entry HANYA saat bar baru (Sangat disarankan untuk M1)

//--- Global Variables
CTrade         trade;
int            hFastM1, hSlowM1, hADX, hFastM5, hSlowM5;
double         m_pip;
double         initialBalance;
datetime       lastBarTime = 0;          // Untuk deteksi bar baru

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   if(_Digits == 3 || _Digits == 5) m_pip = _Point * 10;
   else m_pip = _Point;

   hFastM1 = iMA(_Symbol, PERIOD_M1, InpFastEMA_M1, 0, MODE_EMA, PRICE_CLOSE);
   hSlowM1 = iMA(_Symbol, PERIOD_M1, InpSlowEMA_M1, 0, MODE_EMA, PRICE_CLOSE);
   hADX    = iADX(_Symbol, PERIOD_M1, InpADXPeriod);
   hFastM5 = iMA(_Symbol, InpTrendTF, InpFastEMA_M5, 0, MODE_EMA, PRICE_CLOSE);
   hSlowM5 = iMA(_Symbol, InpTrendTF, InpSlowEMA_M5, 0, MODE_EMA, PRICE_CLOSE);

   if(hFastM1 == INVALID_HANDLE || hSlowM1 == INVALID_HANDLE || hADX == INVALID_HANDLE || 
      hFastM5 == INVALID_HANDLE || hSlowM5 == INVALID_HANDLE) return(INIT_FAILED);

   initialBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   trade.SetExpertMagicNumber(123456);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // 1. Drawdown & Spread Protection
   if((initialBalance - AccountInfoDouble(ACCOUNT_EQUITY)) / initialBalance * 100.0 >= InpMaxDrawdown) return;
   if(SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpread) return;

   // 2. Deteksi Bar Baru (Jika diaktifkan)
   if(InpOnlyOnBarOpen)
   {
      datetime currentBarTime = iTime(_Symbol, PERIOD_M1, 0);
      if(currentBarTime == lastBarTime) 
      {
         // Tetap jalankan Trailing Stop setiap tick, tapi jangan Entry
         ManagePositions();
         return;
      }
      lastBarTime = currentBarTime;
   }

   // 3. Get Data (M1 & M5)
   double fM1[2], sM1[2], adx[2], pDI[2], mDI[2], fM5[2], sM5[2];
   if(CopyBuffer(hFastM1, 0, 0, 2, fM1) < 2 || CopyBuffer(hSlowM1, 0, 0, 2, sM1) < 2 ||
      CopyBuffer(hADX, 0, 0, 2, adx) < 2 || CopyBuffer(hADX, 1, 0, 2, pDI) < 2 ||
      CopyBuffer(hADX, 2, 0, 2, mDI) < 2 || CopyBuffer(hFastM5, 0, 0, 2, fM5) < 2 ||
      CopyBuffer(hSlowM5, 0, 0, 2, sM5) < 2) return;

   // 4. Trend & Signal Logic
   bool isTrendUp_M5   = (fM5[1] > sM5[1]);
   bool isTrendDown_M5 = (fM5[1] < sM5[1]);
   
   int openTrades = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(PositionGetSymbol(i) == _Symbol && PositionGetInteger(POSITION_MAGIC) == 123456) openTrades++;

   // 5. Entry
   if(openTrades < InpMaxOpenTrades)
   {
      // Buy: M5 Up + M1 Fast Cross Slow Up + ADX Strong
      if(isTrendUp_M5 && fM1[1] > sM1[1] && adx[1] > InpADXThreshold && pDI[1] > mDI[1])
      {
         double sl = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - InpStopLoss * m_pip;
         double tp = SymbolInfoDouble(_Symbol, SYMBOL_ASK) + InpTakeProfit * m_pip;
         double lot = CalculateLotSize(InpStopLoss);
         trade.Buy(lot, _Symbol, 0, sl, tp, "Robust M1-M5");
      }
      // Sell: M5 Down + M1 Fast Cross Slow Down + ADX Strong
      else if(isTrendDown_M5 && fM1[1] < sM1[1] && adx[1] > InpADXThreshold && mDI[1] > pDI[1])
      {
         double sl = SymbolInfoDouble(_Symbol, SYMBOL_BID) + InpStopLoss * m_pip;
         double tp = SymbolInfoDouble(_Symbol, SYMBOL_BID) - InpTakeProfit * m_pip;
         double lot = CalculateLotSize(InpStopLoss);
         trade.Sell(lot, _Symbol, 0, sl, tp, "Robust M1-M5");
      }
   }

   // 6. Selalu jalankan Management
   ManagePositions();
}

//+------------------------------------------------------------------+
//| Perhitungan Lot Berbasis Resiko                                  |
//+------------------------------------------------------------------+
double CalculateLotSize(int slPips)
{
   double riskAmount = AccountInfoDouble(ACCOUNT_BALANCE) * (InpRiskPercent / 100.0);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickValue <= 0 || slPips <= 0) return 0.01;
   double lot = riskAmount / ((slPips * m_pip) * (tickValue / tickSize));
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lot = MathFloor(lot / step) * step;
   return MathMax(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), MathMin(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX), lot));
}

//+------------------------------------------------------------------+
//| Management Posisi & Trailing Stop                                |
//+------------------------------------------------------------------+
void ManagePositions()
{
   long stopLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minDistance = (stopLevel + 5) * _Point;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket) && PositionGetInteger(POSITION_MAGIC) == 123456)
      {
         ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
         double currentSL = PositionGetDouble(POSITION_SL);
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         
         if(type == POSITION_TYPE_BUY)
         {
            double newSL = bid - InpTrailingStop * m_pip;
            if(bid > openPrice + (InpTrailingStop * m_pip) && newSL > currentSL + _Point && (bid - newSL) > minDistance)
               trade.PositionModify(ticket, newSL, PositionGetDouble(POSITION_TP));
         }
         else if(type == POSITION_TYPE_SELL)
         {
            double newSL = ask + InpTrailingStop * m_pip;
            if(ask < openPrice - (InpTrailingStop * m_pip) && (newSL < currentSL - _Point || currentSL == 0) && (newSL - ask) > minDistance)
               trade.PositionModify(ticket, newSL, PositionGetDouble(POSITION_TP));
         }
      }
   }
}
