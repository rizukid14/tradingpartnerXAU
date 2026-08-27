//+------------------------------------------------------------------+
//|                                            LuxAlgo_SMC_MT5.mq5   |
//|                             Copyright 2026, RizukiD Quant Team   |
//|                         https://github.com/rizukid14/tradingpartnerXAU |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, RizukiD Quant Team"
#property link      "https://github.com/rizukid14/tradingpartnerXAU"
#property version   "3.50"
#property indicator_chart_window
#property indicator_buffers 0
#property indicator_plots   0

//--- Input Parameters (Curated Muted Palette for Black Backgrounds)
input string   InpGroup1            = "=== 1. Structure & Swings ===";
input int      InpSwingLength       = 5;              // Swing Lookback Bars
input bool     InpShowBOS           = true;           // Show BOS & CHoCH Lines
input bool     InpShowLabels        = false;          // Show HH/HL/LH/LL Labels
input color    InpBOSBullColor      = C'85,150,225';  // Bullish BOS / CHoCH Line (Soft Ice Blue)
input color    InpBOSBearColor      = C'220,95,110';  // Bearish BOS / CHoCH Line (Soft Rose Red)

input string   InpGroup2            = "=== 2. Order Blocks (Muted Tint) ===";
input bool     InpShowOB            = true;           // Show Order Blocks
input int      InpMaxOB             = 2;              // Max Recent Active OBs per side
input color    InpBullOBColor       = C'25,48,72';    // Bullish OB (Muted Dark Slate Blue)
input color    InpBearOBColor       = C'68,30,38';    // Bearish OB (Muted Dark Wine/Rose)

input string   InpGroup3            = "=== 3. Fair Value Gaps (Muted Tint) ===";
input bool     InpShowFVG           = true;           // Show Fair Value Gaps
input int      InpMaxFVG            = 2;              // Max Recent Active FVGs per side
input color    InpBullFVGColor      = C'20,52,42';    // Bullish FVG (Muted Deep Pine Teal)
input color    InpBearFVGColor      = C'62,32,30';    // Bearish FVG (Muted Deep Terracotta)

input string   InpGroup4            = "=== 4. Dealing Range & Discount/Premium Zones ===";
input bool     InpShowDealingRange  = true;           // Show Dealing Range (100-bar)
input int      InpRangeBars         = 100;            // Dealing Range Lookback Bars
input color    InpRangeHighColor    = C'220,95,110';  // 100% Range High Line (Soft Rose Red)
input color    InpPremiumColor      = C'48,22,26';    // Premium Zone Box (61.8% - 100%)
input color    InpEquilibriumColor  = C'120,135,155'; // Equilibrium 50% Line (Slate Gray)
input color    InpDiscountColor     = C'18,44,35';    // Discount Zone Box (0% - 38.2%)
input color    InpRangeLowColor     = C'85,190,140';  // 0% Range Low Line (Soft Emerald Green)

input string   InpGroup5            = "=== 5. Equal Highs & Equal Lows (EQH/EQL) ===";
input bool     InpShowEQH           = true;           // Show Equal Highs / Lows (Liquidity Pools)
input double   InpEQHThresholdATR   = 0.10;           // ATR Tolerance Threshold (0.10 = 10% ATR)
input color    InpEQHColor          = C'220,95,110';  // EQH Dotted Line & Tag (Soft Rose Red)
input color    InpEQLColor          = C'85,190,140';  // EQL Dotted Line & Tag (Soft Emerald Green)

//--- Internal State Structs
struct SwingPoint {
   int      bar_index;
   datetime time;
   double   price;
   string   type;
};

struct OrderBlock {
   datetime time_start;
   datetime time_end;
   double   top;
   double   bottom;
   int      direction; // 1 = Bullish, -1 = Bearish
   bool     mitigated;
};

//--- Global Dynamic Storage
string g_prefix = "SMC_LUX_";

int OnInit()
{
   ObjectsDeleteAll(0, g_prefix);
   ChartRedraw(0);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, g_prefix);
   ChartRedraw(0);
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   if(rates_total < InpSwingLength * 2 + 50) return(0);

   ArraySetAsSeries(time, true);
   ArraySetAsSeries(open, true);
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(close, true);

   ObjectsDeleteAll(0, g_prefix);

   int limit = MathMin(rates_total - InpSwingLength - 1, 200);

   // 1. Detect Swing Pivots
   SwingPoint swing_highs[];
   SwingPoint swing_lows[];
   ArrayResize(swing_highs, 0);
   ArrayResize(swing_lows, 0);

   for(int i = limit; i >= InpSwingLength; i--)
   {
      // Swing High
      bool is_sh = true;
      for(int k = 1; k <= InpSwingLength; k++)
      {
         if(high[i] <= high[i - k] || high[i] <= high[i + k]) { is_sh = false; break; }
      }
      if(is_sh)
      {
         int count = ArraySize(swing_highs);
         ArrayResize(swing_highs, count + 1);
         swing_highs[count].bar_index = i;
         swing_highs[count].time = time[i];
         swing_highs[count].price = high[i];
         if(count > 0 && high[i] > swing_highs[count - 1].price)
            swing_highs[count].type = "HH";
         else
            swing_highs[count].type = "LH";

         if(InpShowLabels)
         {
            string lbl_name = g_prefix + "LBL_SH_" + IntegerToString(i);
            ObjectCreate(0, lbl_name, OBJ_TEXT, 0, time[i], high[i]);
            ObjectSetString(0, lbl_name, OBJPROP_TEXT, swing_highs[count].type);
            ObjectSetString(0, lbl_name, OBJPROP_FONT, "Segoe UI");
            ObjectSetInteger(0, lbl_name, OBJPROP_COLOR, InpBOSBearColor);
            ObjectSetInteger(0, lbl_name, OBJPROP_FONTSIZE, 7);
            ObjectSetInteger(0, lbl_name, OBJPROP_ANCHOR, ANCHOR_LOWER);
            ObjectSetInteger(0, lbl_name, OBJPROP_SELECTABLE, false);
         }
      }

      // Swing Low
      bool is_sl = true;
      for(int k = 1; k <= InpSwingLength; k++)
      {
         if(low[i] >= low[i - k] || low[i] >= low[i + k]) { is_sl = false; break; }
      }
      if(is_sl)
      {
         int count = ArraySize(swing_lows);
         ArrayResize(swing_lows, count + 1);
         swing_lows[count].bar_index = i;
         swing_lows[count].time = time[i];
         swing_lows[count].price = low[i];
         if(count > 0 && low[i] < swing_lows[count - 1].price)
            swing_lows[count].type = "LL";
         else
            swing_lows[count].type = "HL";

         if(InpShowLabels)
         {
            string lbl_name = g_prefix + "LBL_SL_" + IntegerToString(i);
            ObjectCreate(0, lbl_name, OBJ_TEXT, 0, time[i], low[i]);
            ObjectSetString(0, lbl_name, OBJPROP_TEXT, swing_lows[count].type);
            ObjectSetString(0, lbl_name, OBJPROP_FONT, "Segoe UI");
            ObjectSetInteger(0, lbl_name, OBJPROP_COLOR, InpBOSBullColor);
            ObjectSetInteger(0, lbl_name, OBJPROP_FONTSIZE, 7);
            ObjectSetInteger(0, lbl_name, OBJPROP_ANCHOR, ANCHOR_UPPER);
            ObjectSetInteger(0, lbl_name, OBJPROP_SELECTABLE, false);
         }
      }
   }

   // 2. Track BOS / CHoCH & Order Blocks
   int trend_state = 0;
   int last_sh_idx = -1;
   int last_sl_idx = -1;

   OrderBlock obs[];
   ArrayResize(obs, 0);

   for(int i = limit; i >= 0; i--)
   {
      double active_sh = 0.0;
      datetime active_sh_time = 0;
      for(int s = ArraySize(swing_highs) - 1; s >= 0; s--)
      {
         if(swing_highs[s].bar_index > i + InpSwingLength)
         {
            active_sh = swing_highs[s].price;
            active_sh_time = swing_highs[s].time;
            last_sh_idx = swing_highs[s].bar_index;
            break;
         }
      }

      double active_sl = 0.0;
      datetime active_sl_time = 0;
      for(int s = ArraySize(swing_lows) - 1; s >= 0; s--)
      {
         if(swing_lows[s].bar_index > i + InpSwingLength)
         {
            active_sl = swing_lows[s].price;
            active_sl_time = swing_lows[s].time;
            last_sl_idx = swing_lows[s].bar_index;
            break;
         }
      }

      // Bullish Breakout
      if(active_sh > 0 && close[i] > active_sh && close[i+1] <= active_sh)
      {
         string tag = (trend_state == -1) ? "CHoCH" : "BOS";
         trend_state = 1;

         if(InpShowBOS && i < 60)
         {
            string line_name = g_prefix + "BOS_BULL_" + IntegerToString(i);
            ObjectCreate(0, line_name, OBJ_TREND, 0, active_sh_time, active_sh, time[i], active_sh);
            ObjectSetInteger(0, line_name, OBJPROP_COLOR, InpBOSBullColor);
            ObjectSetInteger(0, line_name, OBJPROP_STYLE, (tag == "CHoCH") ? STYLE_SOLID : STYLE_DASH);
            ObjectSetInteger(0, line_name, OBJPROP_WIDTH, 1);
            ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);
            ObjectSetInteger(0, line_name, OBJPROP_SELECTABLE, false);

            string txt_name = g_prefix + "TXT_BULL_" + IntegerToString(i);
            ObjectCreate(0, txt_name, OBJ_TEXT, 0, time[i], active_sh);
            ObjectSetString(0, txt_name, OBJPROP_TEXT, " " + tag);
            ObjectSetString(0, txt_name, OBJPROP_FONT, "Segoe UI");
            ObjectSetInteger(0, txt_name, OBJPROP_COLOR, InpBOSBullColor);
            ObjectSetInteger(0, txt_name, OBJPROP_FONTSIZE, 8);
            ObjectSetInteger(0, txt_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
            ObjectSetInteger(0, txt_name, OBJPROP_SELECTABLE, false);
         }

         // Bullish Order Block (Lowest bar between swing and breakout)
         if(InpShowOB && last_sh_idx > i)
         {
            int min_bar = i;
            double min_p = low[i];
            for(int b = i; b <= last_sh_idx; b++)
            {
               if(low[b] < min_p) { min_p = low[b]; min_bar = b; }
            }
            int oc = ArraySize(obs);
            ArrayResize(obs, oc + 1);
            obs[oc].time_start = time[min_bar];
            obs[oc].top = high[min_bar];
            obs[oc].bottom = low[min_bar];
            obs[oc].direction = 1;
            obs[oc].mitigated = false;
         }
      }

      // Bearish Breakdown
      if(active_sl > 0 && close[i] < active_sl && close[i+1] >= active_sl)
      {
         string tag = (trend_state == 1) ? "CHoCH" : "BOS";
         trend_state = -1;

         if(InpShowBOS && i < 60)
         {
            string line_name = g_prefix + "BOS_BEAR_" + IntegerToString(i);
            ObjectCreate(0, line_name, OBJ_TREND, 0, active_sl_time, active_sl, time[i], active_sl);
            ObjectSetInteger(0, line_name, OBJPROP_COLOR, InpBOSBearColor);
            ObjectSetInteger(0, line_name, OBJPROP_STYLE, (tag == "CHoCH") ? STYLE_SOLID : STYLE_DASH);
            ObjectSetInteger(0, line_name, OBJPROP_WIDTH, 1);
            ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);
            ObjectSetInteger(0, line_name, OBJPROP_SELECTABLE, false);

            string txt_name = g_prefix + "TXT_BEAR_" + IntegerToString(i);
            ObjectCreate(0, txt_name, OBJ_TEXT, 0, time[i], active_sl);
            ObjectSetString(0, txt_name, OBJPROP_TEXT, " " + tag);
            ObjectSetString(0, txt_name, OBJPROP_FONT, "Segoe UI");
            ObjectSetInteger(0, txt_name, OBJPROP_COLOR, InpBOSBearColor);
            ObjectSetInteger(0, txt_name, OBJPROP_FONTSIZE, 8);
            ObjectSetInteger(0, txt_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
            ObjectSetInteger(0, txt_name, OBJPROP_SELECTABLE, false);
         }

         // Bearish Order Block (Highest bar between swing and breakdown)
         if(InpShowOB && last_sl_idx > i)
         {
            int max_bar = i;
            double max_p = high[i];
            for(int b = i; b <= last_sl_idx; b++)
            {
               if(high[b] > max_p) { max_p = high[b]; max_bar = b; }
            }
            int oc = ArraySize(obs);
            ArrayResize(obs, oc + 1);
            obs[oc].time_start = time[max_bar];
            obs[oc].top = high[max_bar];
            obs[oc].bottom = low[max_bar];
            obs[oc].direction = -1;
            obs[oc].mitigated = false;
         }
      }
   }

   // 3. Render Muted Tint Order Blocks (Background Layer)
   if(InpShowOB)
   {
      int drawn_bull = 0;
      int drawn_bear = 0;
      for(int o = ArraySize(obs) - 1; o >= 0; o--)
      {
         bool is_mitigated = false;
         for(int b = 0; b < limit; b++)
         {
            if(time[b] > obs[o].time_start)
            {
               if(obs[o].direction == 1 && close[b] < obs[o].bottom) { is_mitigated = true; break; }
               if(obs[o].direction == -1 && close[b] > obs[o].top)  { is_mitigated = true; break; }
            }
         }
         if(!is_mitigated)
         {
            if(obs[o].direction == 1 && drawn_bull < InpMaxOB)
            {
               string ob_name = g_prefix + "OB_BULL_" + IntegerToString(o);
               ObjectCreate(0, ob_name, OBJ_RECTANGLE, 0, obs[o].time_start, obs[o].top, time[0] + PeriodSeconds()*6, obs[o].bottom);
               ObjectSetInteger(0, ob_name, OBJPROP_COLOR, InpBullOBColor);
               ObjectSetInteger(0, ob_name, OBJPROP_BGCOLOR, InpBullOBColor);
               ObjectSetInteger(0, ob_name, OBJPROP_FILL, true);
               ObjectSetInteger(0, ob_name, OBJPROP_BACK, true);
               ObjectSetInteger(0, ob_name, OBJPROP_SELECTABLE, false);

               string tag_name = g_prefix + "TAG_OB_BULL_" + IntegerToString(o);
               ObjectCreate(0, tag_name, OBJ_TEXT, 0, time[0] + PeriodSeconds()*6, (obs[o].top + obs[o].bottom)/2.0);
               ObjectSetString(0, tag_name, OBJPROP_TEXT, " +OB");
               ObjectSetString(0, tag_name, OBJPROP_FONT, "Segoe UI Semibold");
               ObjectSetInteger(0, tag_name, OBJPROP_COLOR, InpBOSBullColor);
               ObjectSetInteger(0, tag_name, OBJPROP_FONTSIZE, 8);
               ObjectSetInteger(0, tag_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
               ObjectSetInteger(0, tag_name, OBJPROP_SELECTABLE, false);

               drawn_bull++;
            }
            else if(obs[o].direction == -1 && drawn_bear < InpMaxOB)
            {
               string ob_name = g_prefix + "OB_BEAR_" + IntegerToString(o);
               ObjectCreate(0, ob_name, OBJ_RECTANGLE, 0, obs[o].time_start, obs[o].top, time[0] + PeriodSeconds()*6, obs[o].bottom);
               ObjectSetInteger(0, ob_name, OBJPROP_COLOR, InpBearOBColor);
               ObjectSetInteger(0, ob_name, OBJPROP_BGCOLOR, InpBearOBColor);
               ObjectSetInteger(0, ob_name, OBJPROP_FILL, true);
               ObjectSetInteger(0, ob_name, OBJPROP_BACK, true);
               ObjectSetInteger(0, ob_name, OBJPROP_SELECTABLE, false);

               string tag_name = g_prefix + "TAG_OB_BEAR_" + IntegerToString(o);
               ObjectCreate(0, tag_name, OBJ_TEXT, 0, time[0] + PeriodSeconds()*6, (obs[o].top + obs[o].bottom)/2.0);
               ObjectSetString(0, tag_name, OBJPROP_TEXT, " -OB");
               ObjectSetString(0, tag_name, OBJPROP_FONT, "Segoe UI Semibold");
               ObjectSetInteger(0, tag_name, OBJPROP_COLOR, InpBOSBearColor);
               ObjectSetInteger(0, tag_name, OBJPROP_FONTSIZE, 8);
               ObjectSetInteger(0, tag_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
               ObjectSetInteger(0, tag_name, OBJPROP_SELECTABLE, false);

               drawn_bear++;
            }
         }
      }
   }

   // 4. Render Muted Fair Value Gaps (FVG)
   if(InpShowFVG)
   {
      int drawn_bull_fvg = 0;
      int drawn_bear_fvg = 0;
      for(int i = 1; i < limit; i++)
      {
         // Bullish FVG
         if(low[i-1] > high[i+1] && drawn_bull_fvg < InpMaxFVG)
         {
            bool fvg_mit = false;
            for(int k = 0; k < i-1; k++)
            {
               if(low[k] <= high[i+1]) { fvg_mit = true; break; }
            }
            if(!fvg_mit)
            {
               string fvg_name = g_prefix + "FVG_BULL_" + IntegerToString(i);
               ObjectCreate(0, fvg_name, OBJ_RECTANGLE, 0, time[i+1], low[i-1], time[0] + PeriodSeconds()*4, high[i+1]);
               ObjectSetInteger(0, fvg_name, OBJPROP_COLOR, InpBullFVGColor);
               ObjectSetInteger(0, fvg_name, OBJPROP_BGCOLOR, InpBullFVGColor);
               ObjectSetInteger(0, fvg_name, OBJPROP_FILL, true);
               ObjectSetInteger(0, fvg_name, OBJPROP_BACK, true);
               ObjectSetInteger(0, fvg_name, OBJPROP_SELECTABLE, false);

               string tag_name = g_prefix + "TAG_FVG_BULL_" + IntegerToString(i);
               ObjectCreate(0, tag_name, OBJ_TEXT, 0, time[0] + PeriodSeconds()*4, (low[i-1] + high[i+1])/2.0);
               ObjectSetString(0, tag_name, OBJPROP_TEXT, " +FVG");
               ObjectSetString(0, tag_name, OBJPROP_FONT, "Segoe UI Semibold");
               ObjectSetInteger(0, tag_name, OBJPROP_COLOR, C'70,165,130');
               ObjectSetInteger(0, tag_name, OBJPROP_FONTSIZE, 7);
               ObjectSetInteger(0, tag_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
               ObjectSetInteger(0, tag_name, OBJPROP_SELECTABLE, false);

               drawn_bull_fvg++;
            }
         }

         // Bearish FVG
         if(high[i-1] < low[i+1] && drawn_bear_fvg < InpMaxFVG)
         {
            bool fvg_mit = false;
            for(int k = 0; k < i-1; k++)
            {
               if(high[k] >= low[i+1]) { fvg_mit = true; break; }
            }
            if(!fvg_mit)
            {
               string fvg_name = g_prefix + "FVG_BEAR_" + IntegerToString(i);
               ObjectCreate(0, fvg_name, OBJ_RECTANGLE, 0, time[i+1], high[i-1], time[0] + PeriodSeconds()*4, low[i+1]);
               ObjectSetInteger(0, fvg_name, OBJPROP_COLOR, InpBearFVGColor);
               ObjectSetInteger(0, fvg_name, OBJPROP_BGCOLOR, InpBearFVGColor);
               ObjectSetInteger(0, fvg_name, OBJPROP_FILL, true);
               ObjectSetInteger(0, fvg_name, OBJPROP_BACK, true);
               ObjectSetInteger(0, fvg_name, OBJPROP_SELECTABLE, false);

               string tag_name = g_prefix + "TAG_FVG_BEAR_" + IntegerToString(i);
               ObjectCreate(0, tag_name, OBJ_TEXT, 0, time[0] + PeriodSeconds()*4, (high[i-1] + low[i+1])/2.0);
               ObjectSetString(0, tag_name, OBJPROP_TEXT, " -FVG");
               ObjectSetString(0, tag_name, OBJPROP_FONT, "Segoe UI Semibold");
               ObjectSetInteger(0, tag_name, OBJPROP_COLOR, C'210,110,110');
               ObjectSetInteger(0, tag_name, OBJPROP_FONTSIZE, 7);
               ObjectSetInteger(0, tag_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
               ObjectSetInteger(0, tag_name, OBJPROP_SELECTABLE, false);

               drawn_bear_fvg++;
            }
         }
      }
   }

   // 5. Dealing Range, Premium / Discount Zones & Equilibrium
   if(InpShowDealingRange)
   {
      int range_bars = MathMin(InpRangeBars, rates_total);
      int max_idx = ArrayMaximum(high, 0, range_bars);
      int min_idx = ArrayMinimum(low, 0, range_bars);
      double dr_high = high[max_idx];
      double dr_low  = low[min_idx];
      double dr_rng  = MathMax(dr_high - dr_low, _Point);
      double dr_prem = dr_low + 0.618 * dr_rng;
      double dr_eq   = dr_low + 0.500 * dr_rng;
      double dr_disc = dr_low + 0.382 * dr_rng;
      datetime t_start = time[range_bars-1];
      datetime t_end   = time[0] + PeriodSeconds()*8;

      // A. Premium Zone (61.8% to 100% - Sell Zone)
      string box_prem = g_prefix + "ZONE_PREM";
      ObjectCreate(0, box_prem, OBJ_RECTANGLE, 0, t_start, dr_high, t_end, dr_prem);
      ObjectSetInteger(0, box_prem, OBJPROP_COLOR, InpPremiumColor);
      ObjectSetInteger(0, box_prem, OBJPROP_BGCOLOR, InpPremiumColor);
      ObjectSetInteger(0, box_prem, OBJPROP_FILL, true);
      ObjectSetInteger(0, box_prem, OBJPROP_BACK, true);
      ObjectSetInteger(0, box_prem, OBJPROP_SELECTABLE, false);

      // B. Discount Zone (0% to 38.2% - Buy Zone)
      string box_disc = g_prefix + "ZONE_DISC";
      ObjectCreate(0, box_disc, OBJ_RECTANGLE, 0, t_start, dr_disc, t_end, dr_low);
      ObjectSetInteger(0, box_disc, OBJPROP_COLOR, InpDiscountColor);
      ObjectSetInteger(0, box_disc, OBJPROP_BGCOLOR, InpDiscountColor);
      ObjectSetInteger(0, box_disc, OBJPROP_FILL, true);
      ObjectSetInteger(0, box_disc, OBJPROP_BACK, true);
      ObjectSetInteger(0, box_disc, OBJPROP_SELECTABLE, false);

      // C. 100% Range High Line & Tag
      string line_hi = g_prefix + "DR_HIGH";
      ObjectCreate(0, line_hi, OBJ_TREND, 0, t_start, dr_high, t_end, dr_high);
      ObjectSetInteger(0, line_hi, OBJPROP_COLOR, InpRangeHighColor);
      ObjectSetInteger(0, line_hi, OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, line_hi, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, line_hi, OBJPROP_RAY_RIGHT, false);
      ObjectSetInteger(0, line_hi, OBJPROP_SELECTABLE, false);

      string txt_hi = g_prefix + "TXT_HIGH";
      ObjectCreate(0, txt_hi, OBJ_TEXT, 0, t_end, dr_high);
      ObjectSetString(0, txt_hi, OBJPROP_TEXT, " [100% High: " + DoubleToString(dr_high, _Digits) + "]");
      ObjectSetString(0, txt_hi, OBJPROP_FONT, "Segoe UI Semibold");
      ObjectSetInteger(0, txt_hi, OBJPROP_COLOR, InpRangeHighColor);
      ObjectSetInteger(0, txt_hi, OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, txt_hi, OBJPROP_ANCHOR, ANCHOR_LEFT);
      ObjectSetInteger(0, txt_hi, OBJPROP_SELECTABLE, false);

      // D. Premium Boundary Tag (61.8%)
      string txt_prem = g_prefix + "TXT_PREM";
      ObjectCreate(0, txt_prem, OBJ_TEXT, 0, t_end, dr_prem);
      ObjectSetString(0, txt_prem, OBJPROP_TEXT, " [Premium 61.8%: " + DoubleToString(dr_prem, _Digits) + "]");
      ObjectSetString(0, txt_prem, OBJPROP_FONT, "Segoe UI");
      ObjectSetInteger(0, txt_prem, OBJPROP_COLOR, InpRangeHighColor);
      ObjectSetInteger(0, txt_prem, OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, txt_prem, OBJPROP_ANCHOR, ANCHOR_LEFT);
      ObjectSetInteger(0, txt_prem, OBJPROP_SELECTABLE, false);

      // E. 50% Equilibrium Line & Tag
      string line_eq = g_prefix + "DR_EQ";
      ObjectCreate(0, line_eq, OBJ_TREND, 0, t_start, dr_eq, t_end, dr_eq);
      ObjectSetInteger(0, line_eq, OBJPROP_COLOR, InpEquilibriumColor);
      ObjectSetInteger(0, line_eq, OBJPROP_STYLE, STYLE_DOT);
      ObjectSetInteger(0, line_eq, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, line_eq, OBJPROP_RAY_RIGHT, false);
      ObjectSetInteger(0, line_eq, OBJPROP_SELECTABLE, false);

      string txt_eq = g_prefix + "TXT_EQ";
      ObjectCreate(0, txt_eq, OBJ_TEXT, 0, t_end, dr_eq);
      ObjectSetString(0, txt_eq, OBJPROP_TEXT, " [50% EQ: " + DoubleToString(dr_eq, _Digits) + "]");
      ObjectSetString(0, txt_eq, OBJPROP_FONT, "Segoe UI");
      ObjectSetInteger(0, txt_eq, OBJPROP_COLOR, InpEquilibriumColor);
      ObjectSetInteger(0, txt_eq, OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, txt_eq, OBJPROP_ANCHOR, ANCHOR_LEFT);
      ObjectSetInteger(0, txt_eq, OBJPROP_SELECTABLE, false);

      // F. Discount Boundary Tag (38.2%)
      string txt_disc = g_prefix + "TXT_DISC";
      ObjectCreate(0, txt_disc, OBJ_TEXT, 0, t_end, dr_disc);
      ObjectSetString(0, txt_disc, OBJPROP_TEXT, " [Discount 38.2%: " + DoubleToString(dr_disc, _Digits) + "]");
      ObjectSetString(0, txt_disc, OBJPROP_FONT, "Segoe UI");
      ObjectSetInteger(0, txt_disc, OBJPROP_COLOR, InpRangeLowColor);
      ObjectSetInteger(0, txt_disc, OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, txt_disc, OBJPROP_ANCHOR, ANCHOR_LEFT);
      ObjectSetInteger(0, txt_disc, OBJPROP_SELECTABLE, false);

      // G. 0% Range Low Line & Tag
      string line_lo = g_prefix + "DR_LOW";
      ObjectCreate(0, line_lo, OBJ_TREND, 0, t_start, dr_low, t_end, dr_low);
      ObjectSetInteger(0, line_lo, OBJPROP_COLOR, InpRangeLowColor);
      ObjectSetInteger(0, line_lo, OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, line_lo, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, line_lo, OBJPROP_RAY_RIGHT, false);
      ObjectSetInteger(0, line_lo, OBJPROP_SELECTABLE, false);

      string txt_lo = g_prefix + "TXT_LOW";
      ObjectCreate(0, txt_lo, OBJ_TEXT, 0, t_end, dr_low);
      ObjectSetString(0, txt_lo, OBJPROP_TEXT, " [0% Low: " + DoubleToString(dr_low, _Digits) + "]");
      ObjectSetString(0, txt_lo, OBJPROP_FONT, "Segoe UI Semibold");
      ObjectSetInteger(0, txt_lo, OBJPROP_COLOR, InpRangeLowColor);
      ObjectSetInteger(0, txt_lo, OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, txt_lo, OBJPROP_ANCHOR, ANCHOR_LEFT);
      ObjectSetInteger(0, txt_lo, OBJPROP_SELECTABLE, false);
   }

   // 6. Equal Highs (EQH) & Equal Lows (EQL) Liquidity Pool Dotted Lines (Recent Active Only)
   if(InpShowEQH)
   {
      // Calculate ATR(14) for EQH/EQL tolerance
      int atr_period = 14;
      double tr_sum = 0.0;
      for(int a = 1; a <= atr_period && a < rates_total - 1; a++)
      {
         double tr = MathMax(high[a] - low[a], MathMax(MathAbs(high[a] - close[a+1]), MathAbs(low[a] - close[a+1])));
         tr_sum += tr;
      }
      double atr_val = tr_sum / MathMax(atr_period, 1);
      if(atr_val <= 0.0) atr_val = _Point * 30;
      double eq_dist = InpEQHThresholdATR * atr_val;

      // Detect & Render Recent EQH (Max 2 recent unmitigated)
      int sh_size = ArraySize(swing_highs);
      int drawn_eqh = 0;
      for(int i = sh_size - 1; i >= 1 && drawn_eqh < 2; i--)
      {
         for(int j = i - 1; j >= 0; j--)
         {
            if(MathAbs(swing_highs[i].price - swing_highs[j].price) <= eq_dist)
            {
               double p_avg = (swing_highs[i].price + swing_highs[j].price) / 2.0;
               datetime t_start = swing_highs[j].time;
               datetime t_end   = swing_highs[i].time;

               // Check if already blown through / mitigated
               bool mit = false;
               for(int b = swing_highs[i].bar_index - 1; b >= 0; b--)
               {
                  if(close[b] > p_avg + eq_dist) { mit = true; break; }
               }
               if(mit) continue;

               string line_name = g_prefix + "EQH_LINE_" + IntegerToString(drawn_eqh);
               ObjectCreate(0, line_name, OBJ_TREND, 0, t_start, p_avg, t_end, p_avg);
               ObjectSetInteger(0, line_name, OBJPROP_COLOR, InpEQHColor);
               ObjectSetInteger(0, line_name, OBJPROP_STYLE, STYLE_DOT);
               ObjectSetInteger(0, line_name, OBJPROP_WIDTH, 1);
               ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);
               ObjectSetInteger(0, line_name, OBJPROP_SELECTABLE, false);

               datetime t_mid = (datetime)(((long)t_start + (long)t_end) / 2);
               string txt_name = g_prefix + "EQH_TXT_" + IntegerToString(drawn_eqh);
               ObjectCreate(0, txt_name, OBJ_TEXT, 0, t_mid, p_avg + _Point * 8);
               ObjectSetString(0, txt_name, OBJPROP_TEXT, "EQH");
               ObjectSetString(0, txt_name, OBJPROP_FONT, "Segoe UI Semibold");
               ObjectSetInteger(0, txt_name, OBJPROP_COLOR, InpEQHColor);
               ObjectSetInteger(0, txt_name, OBJPROP_FONTSIZE, 7);
               ObjectSetInteger(0, txt_name, OBJPROP_ANCHOR, ANCHOR_LOWER);
               ObjectSetInteger(0, txt_name, OBJPROP_SELECTABLE, false);

               drawn_eqh++;
               break;
            }
         }
      }

      // Detect & Render Recent EQL (Max 2 recent unmitigated)
      int sl_size = ArraySize(swing_lows);
      int drawn_eql = 0;
      for(int i = sl_size - 1; i >= 1 && drawn_eql < 2; i--)
      {
         for(int j = i - 1; j >= 0; j--)
         {
            if(MathAbs(swing_lows[i].price - swing_lows[j].price) <= eq_dist)
            {
               double p_avg = (swing_lows[i].price + swing_lows[j].price) / 2.0;
               datetime t_start = swing_lows[j].time;
               datetime t_end   = swing_lows[i].time;

               // Check if already blown through / mitigated
               bool mit = false;
               for(int b = swing_lows[i].bar_index - 1; b >= 0; b--)
               {
                  if(close[b] < p_avg - eq_dist) { mit = true; break; }
               }
               if(mit) continue;

               string line_name = g_prefix + "EQL_LINE_" + IntegerToString(drawn_eql);
               ObjectCreate(0, line_name, OBJ_TREND, 0, t_start, p_avg, t_end, p_avg);
               ObjectSetInteger(0, line_name, OBJPROP_COLOR, InpEQLColor);
               ObjectSetInteger(0, line_name, OBJPROP_STYLE, STYLE_DOT);
               ObjectSetInteger(0, line_name, OBJPROP_WIDTH, 1);
               ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);
               ObjectSetInteger(0, line_name, OBJPROP_SELECTABLE, false);

               datetime t_mid = (datetime)(((long)t_start + (long)t_end) / 2);
               string txt_name = g_prefix + "EQL_TXT_" + IntegerToString(drawn_eql);
               ObjectCreate(0, txt_name, OBJ_TEXT, 0, t_mid, p_avg - _Point * 8);
               ObjectSetString(0, txt_name, OBJPROP_TEXT, "EQL");
               ObjectSetString(0, txt_name, OBJPROP_FONT, "Segoe UI Semibold");
               ObjectSetInteger(0, txt_name, OBJPROP_COLOR, InpEQLColor);
               ObjectSetInteger(0, txt_name, OBJPROP_FONTSIZE, 7);
               ObjectSetInteger(0, txt_name, OBJPROP_ANCHOR, ANCHOR_UPPER);
               ObjectSetInteger(0, txt_name, OBJPROP_SELECTABLE, false);

               drawn_eql++;
               break;
            }
         }
      }
   }

   ChartRedraw(0);
   return(rates_total);
}
//+------------------------------------------------------------------+
