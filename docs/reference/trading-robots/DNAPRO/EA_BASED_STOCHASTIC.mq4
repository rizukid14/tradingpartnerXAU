//+------------------------------------------------------------------+
//|                                           EA_BASED_STOCHASIC.mq4 |
//|                                      Denny Wijaya Alambai - 2021 |
//+------------------------------------------------------------------+
#property copyright "STOCHASTIC + BE + TS Denny Wijaya Alambai - 2021"
#property version   "1.00"
#property strict
//+------------------------------------------------------------------+
#include <stderror.mqh>;
#include <stdlib.mqh>;
//+------------------------------------------------------------------+
// Variables for Magic Number dan Nama EA
int MagicNumber;
string EA_ID = "12", Pair_ID, Period_ID, Period_Name;
string EANAME = "EA_BASED_STOCHASTIC";
//--
input string notes = "EA based Stochastic";
input double Lots = 0.01;
input double MaximumRisk = 0.02;
input double DecreaseFactor = 3;
input string notes1 = "--------------";
input int stochK      = 4; // Stoch K Period
input int stochD      = 2; // Stoch D Period
input int stochS      = 3; // Stoch S Period
input int stochBawah  = 30; // Stoch level buy
input int stochAtas   = 70; // Stoch level sell
input int targetPoint = 1000; // Target point
double stopLevel;
double minLotSize;
double TrailingStop;
double TrailingStep = 1;
//+------------------------------------------------------------------+
double MyAccountBalance;
double MyAccountMargin;
double FreeAccountMargin;
string MyBroker;
double MyAccountEquity;
double MinimumBalance;
double PercentageBalance;
double MyAccMarginLevel;
double MyAccProfit;
//+------------------------------------------------------------------+
// Creating a variable to store the time when a new candle start.
// Populating the variable with the current server time.
datetime NewCandleTime = TimeCurrent();
//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   GenerateMagicNumber();
   stopLevel  = MarketInfo(Symbol(), MODE_STOPLEVEL);
   TrailingStop = stopLevel * 10;
   minLotSize = MarketInfo(Symbol(), MODE_MINLOT);
   TampilkanNamaEA();
   return(INIT_SUCCEEDED);
  }
//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
//---
  }
//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
  {
//MoveToBreakEven();
   DisplayEADetail();
   TrailingStop();
   if(IsNewCandle())
     {
      double K0 = iStochastic(_Symbol, _Period, stochK, stochD, stochS, MODE_SMA, 0, MODE_MAIN, 0);
      double D0 = iStochastic(_Symbol, _Period, stochK, stochD, stochS, MODE_SMA, 0, MODE_SIGNAL, 0);
      double K1 = iStochastic(_Symbol, _Period, stochK, stochD, stochS, MODE_SMA, 0, MODE_MAIN, 1);
      double D1 = iStochastic(_Symbol, _Period, stochK, stochD, stochS, MODE_SMA, 0, MODE_SIGNAL, 1);
      //--
      if(OrdersTotal() == 0)
         if((K0 > stochBawah) && (D0 > stochBawah))
            if((D0 > K0) && (D1 < K1))
              {
               RefreshRates();
               double SLoss = Ask - TrailingStop * _Point;
               double TPoint = Ask + targetPoint * _Point;
               int ticket = OrderSend(_Symbol, OP_BUY, LotsOptimized(), Ask, 3, SLoss, TPoint, EANAME + "-" + Period_Name, MagicNumber, 0, clrGreen);
               if(ticket < 0)
                  ExpertRemove();
               return;
              }
      //--
      if(OrdersTotal() == 0)
         if((K0 < stochAtas) && (D0 < stochAtas))
            if((D0 < K0) && (D1 > K1))
              {
               RefreshRates();
               double SLoss = Bid + TrailingStop * _Point;
               double TPoint = Bid - targetPoint * _Point;
               int ticket = OrderSend(_Symbol, OP_SELL, LotsOptimized(), Bid, 3, SLoss, TPoint, EANAME + "-" + Period_Name, MagicNumber, 0, clrRed);
               if(ticket < 0)
                  ExpertRemove();
               return;
              }
     }
  }
//+------------------------------------------------------------------+
bool IsNewCandle()
  {
// If the time of the candle when the function ran last
// is the same as the time this candle started,
// return false, because it is not a new candle.
   if(NewCandleTime == iTime(Symbol(), Period(), 0))
      return false;
// Otherwise, it is a new candle and we need to return true.
   else
     {
      // If it is a new candle, then we store the new value.
      NewCandleTime = iTime(Symbol(), Period(), 0);
      return true;
     }
  }
//+------------------------------------------------------------------+
void MoveToBreakEven()

  {
   for(int buyCnt = OrdersTotal() - 1; buyCnt >= 0; buyCnt--)
     {
      if(OrderSelect(buyCnt, SELECT_BY_POS, MODE_TRADES))
         if(OrderMagicNumber() != MagicNumber)
            continue;
      if(OrderSymbol() == Symbol())
         if(OrderType() == OP_BUY)
            if(Bid - OrderOpenPrice() > stopLevel * _Point)
               if(OrderOpenPrice() > OrderStopLoss())
                  if(!OrderModify(OrderTicket(), OrderOpenPrice(), OrderOpenPrice() + (TrailingStep * _Point), OrderTakeProfit(), 0, CLR_NONE))
                     Print("eror");
     }
   for(int sellCnt = OrdersTotal() - 1; sellCnt >= 0; sellCnt--)
     {
      if(OrderSelect(sellCnt, SELECT_BY_POS, MODE_TRADES))
         if(OrderMagicNumber() != MagicNumber)
            continue;
      if(OrderSymbol() == Symbol())
         if(OrderType() == OP_SELL)
            if(OrderOpenPrice() - Ask > stopLevel * _Point)
               if(OrderOpenPrice() < OrderStopLoss())
                  if(!OrderModify(OrderTicket(), OrderOpenPrice(), OrderOpenPrice() - (TrailingStep * _Point), OrderTakeProfit(), 0, CLR_NONE))
                     Print("eror");
     }
  }
//+------------------------------------------------------------------+
//| Expert custom function                                           |
//+------------------------------------------------------------------+
void TrailingStop()
  {
   for(int i = 0; i < OrdersTotal(); i++) // Counter untuk mencari order yang sedang berlangsung
     {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) // Pilih order berdasarkan posisi yang pertama
        {
         if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber) // Jika ketemu order berdasarkan simbol
           {
            double marketBid, marketAsk, marketPoint;
            //----
            marketPoint = MarketInfo(OrderSymbol(), MODE_POINT);
            if(OrderType() == OP_BUY)
              {
               marketBid = MarketInfo(OrderSymbol(), MODE_BID);
               if(marketBid - OrderOpenPrice() > TrailingStop * marketPoint)
                 {
                  if(OrderStopLoss() < marketBid - (TrailingStop + TrailingStep - 1)* marketPoint)
                    {
                     ModifyStopLoss(marketBid - TrailingStop * marketPoint);
                     return;
                    }
                 }
              }
            if(OrderType() == OP_SELL)
              {
               marketAsk = MarketInfo(OrderSymbol(), MODE_ASK);
               if(OrderOpenPrice() - marketAsk > TrailingStop * marketPoint)
                 {
                  if(OrderStopLoss() > marketAsk + (TrailingStop + TrailingStep - 1)* marketPoint || OrderStopLoss() == 0)
                    {
                     ModifyStopLoss(marketAsk + TrailingStop * marketPoint);
                     return;
                    }
                 }
              }
           }
        }
     }
  }
//+------------------------------------------------------------------+
//| Expert custom function                                           |
//+------------------------------------------------------------------+
void ModifyStopLoss(double OrderSL)
  {
   bool result;
   result = OrderModify(OrderTicket(), OrderOpenPrice(), OrderSL, OrderTakeProfit(), 0, CLR_NONE);
  }
//+------------------------------------------------------------------+
//| Expert custom function                                           |
//+------------------------------------------------------------------+
void GenerateMagicNumber()
  {
   string MagicText;
   GetPeriodNumber();
   GetPeriodSymbol();
   MagicText = EA_ID + Pair_ID + Period_ID;
   MagicNumber = StrToInteger(MagicText);
   return;
  }
//+------------------------------------------------------------------+
//| Expert custom function                                           |
//+------------------------------------------------------------------+
void GetPeriodNumber()
  {
   switch(Period())
     {
      case PERIOD_MN1:
         Period_ID = "9";
         Period_Name = "MN1";
         break;
      case PERIOD_W1:
         Period_ID = "8";
         Period_Name = "W1";
         break;
      case PERIOD_D1:
         Period_ID = "7";
         Period_Name = "D1";
         break;
      case PERIOD_H4:
         Period_ID = "6";
         Period_Name = "H4";
         break;
      case PERIOD_H1:
         Period_ID = "5";
         Period_Name = "H1";
         break;
      case PERIOD_M30:
         Period_ID = "4";
         Period_Name = "M30";
         break;
      case PERIOD_M15:
         Period_ID = "3";
         Period_Name = "M15";
         break;
      case PERIOD_M5:
         Period_ID = "2";
         Period_Name = "M5";
         break;
      case PERIOD_M1:
         Period_ID = "1";
         Period_Name = "M1";
         break;
     }
   return;
  }
//+------------------------------------------------------------------+
//| Expert custom function                                           |
//+------------------------------------------------------------------+
void GetPeriodSymbol()
  {
   int counter, totals = SymbolsTotal(false);
   for(counter = 0 ; counter < totals ; counter++)
     {
      if(_Symbol == SymbolName(counter, true))
         Pair_ID = IntegerToString(counter);
     }
   return;
  }
//+------------------------------------------------------------------+
//| Expert custom function                                           |
//+------------------------------------------------------------------+
void TampilkanNamaEA()
  {
   ObjectCreate("EA_NAME", OBJ_LABEL, 0, 0, 0);
   ObjectSet("EA_NAME", OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSet("EA_NAME", OBJPROP_XDISTANCE, 20);
   ObjectSet("EA_NAME", OBJPROP_YDISTANCE, 20);
   ObjectSetText("EA_NAME", EANAME, 14, "Arial", Red);
  }
//+------------------------------------------------------------------+
//| Expert custom function                                           |
//+------------------------------------------------------------------+
void DisplayEADetail()
  {
   MyBroker          = AccountCompany();
   MyAccountBalance  = AccountInfoDouble(ACCOUNT_BALANCE);
   MyAccountMargin   = AccountInfoDouble(ACCOUNT_MARGIN);
   FreeAccountMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   MyAccountEquity   = AccountInfoDouble(ACCOUNT_EQUITY);
   MyAccMarginLevel  = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   MyAccProfit       = AccountInfoDouble(ACCOUNT_PROFIT);
// Display text on chart
   Comment("\n", "\n",
           "My Broker--------: ", MyBroker, "\n",
           "My Account Bal---: ", MyAccountBalance, "\n",
           "My Account Margin: ", MyAccountMargin, "\n",
           "My Free Margin---: ", FreeAccountMargin, "\n",
           "My Equity--------: ", MyAccountEquity, "\n",
           "My Margin Level--: ", MyAccMarginLevel, "\n",
           "My Acount Profit : ", MyAccProfit, "\n",
           "My Magic Number  : ", MagicNumber
          );
  }
//+------------------------------------------------------------------+
//| Calculate optimal lot size                                       |
//+------------------------------------------------------------------+
double LotsOptimized()
  {
   double lot = Lots;
   int    orders = HistoryTotal();   // history orders total
   int    losses = 0;                // number of losses orders without a break
//--- select lot size
   lot = NormalizeDouble(AccountFreeMargin() * MaximumRisk / 1000.0, 1);
//--- calcuulate number of losses orders without a break
   if(DecreaseFactor > 0)
     {
      for(int i = orders - 1; i >= 0; i--)
        {
         if(OrderSelect(i, SELECT_BY_POS, MODE_HISTORY) == false)
           {
            Print("Error in history!");
            break;
           }
         if(OrderSymbol() != Symbol() || OrderType() > OP_SELL)
            continue;
         //---
         if(OrderProfit() > 0)
            break;
         if(OrderProfit() < 0)
            losses++;
        }
      if(losses > 1)
         lot = NormalizeDouble(lot - lot * losses / DecreaseFactor, 1);
     }
//--- return lot size
   if(lot < 0.01)
      lot = 0.01;
   return(lot);
  }
//+------------------------------------------------------------------+
