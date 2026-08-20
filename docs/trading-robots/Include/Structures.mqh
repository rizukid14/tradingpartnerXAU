//+------------------------------------------------------------------+
//|                                                  Structures.mqh  |
//|                          GoldSnD EA - Shared Data Structures      |
//+------------------------------------------------------------------+
#ifndef __GOLDSD_STRUCTURES_MQH__
#define __GOLDSD_STRUCTURES_MQH__

enum ENUM_ZONE_TYPE
{
   ZONE_DEMAND = 0,
   ZONE_SUPPLY = 1
};

enum ENUM_HTF_BIAS
{
   BIAS_BULLISH  =  1,
   BIAS_BEARISH  = -1,
   BIAS_NEUTRAL  =  0
};

struct SZone
{
   ENUM_ZONE_TYPE type;
   double         upper;
   double         lower;
   datetime       birthTime;
   int            birthBar;
   bool           fresh;
   bool           active;
   string         id;
   void Reset()
   {
      type=ZONE_DEMAND; upper=0; lower=0; birthTime=0;
      birthBar=0; fresh=true; active=true; id="";
   }
};

struct SLiquidityPool
{
   double   level;
   int      touchCount;
   bool     isHighPool;
   bool     swept;
   datetime firstTouch;
   datetime lastTouch;
   string   id;
   void Reset()
   {
      level=0; touchCount=0; isHighPool=false; swept=false;
      firstTouch=0; lastTouch=0; id="";
   }
};

struct SEntrySignal
{
   bool             valid;
   ENUM_ORDER_TYPE  direction;
   double           entryPrice;
   double           slPrice;
   double           tp1Price;
   double           tp2Price;
   double           tp3Price;
   double           lotSize;
   datetime         signalTime;
   string           reason;
   void Reset()
   {
      valid=false; direction=ORDER_TYPE_BUY; entryPrice=0;
      slPrice=0; tp1Price=0; tp2Price=0; tp3Price=0;
      lotSize=0; signalTime=0; reason="";
   }
};

struct SPositionTracker
{
   ulong            ticket;
   double           entryPrice;
   double           originalLots;
   double           tp1Price;
   double           tp3Price;
   double           initialSL;
   bool             tp1Hit;
   bool             trailingActive;
   ENUM_ORDER_TYPE  direction;
   void Reset()
   {
      ticket=0; entryPrice=0; originalLots=0; tp1Price=0;
      tp3Price=0; initialSL=0; tp1Hit=false; trailingActive=false;
      direction=ORDER_TYPE_BUY;
   }
};

class CPipUtil
{
public:
   static double PipSize(string symbol)
   {
      int digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
      if(digits==3 || digits==5) return point*10.0;
      return point;
   }
   static double PipToPrice(string symbol,double pips)
   { return pips*PipSize(symbol); }
   static double PriceToPip(string symbol,double priceDistance)
   {
      double ps=PipSize(symbol);
      if(ps==0) return 0;
      return priceDistance/ps;
   }
};

#endif
