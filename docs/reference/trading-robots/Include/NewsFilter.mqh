//+------------------------------------------------------------------+
//|                                                   NewsFilter.mqh |
//|                Economic Calendar Blackout Module                 |
//+------------------------------------------------------------------+
#ifndef __GOLDSD_NEWSFILTER_MQH__
#define __GOLDSD_NEWSFILTER_MQH__

//+------------------------------------------------------------------+
//| CNewsFilter - Blocks entries during economic events               |
//+------------------------------------------------------------------+
class CNewsFilter
{
private:
   int               m_highBefore;   // 30 min
   int               m_highAfter;    // 30 min
   int               m_medBefore;    // 15 min
   int               m_medAfter;     // 15 min
   
   string            m_nextEventName;
   datetime          m_nextEventTime;
   bool              m_isBlackout;

public:
   CNewsFilter() : m_nextEventName(""), m_nextEventTime(0), m_isBlackout(false) {}

   void Init(int highBefore, int highAfter, int medBefore, int medAfter)
   {
      m_highBefore = highBefore * 60;
      m_highAfter = highAfter * 60;
      m_medBefore = medBefore * 60;
      m_medAfter = medAfter * 60;
   }

   //--- Check for news blackout (called on timer and before entry)
   bool IsBlackoutActive()
   {
      if(MQLInfoInteger(MQL_TESTER)) return false; // Not supported in tester

      m_isBlackout = false;
      m_nextEventName = "None";
      m_nextEventTime = 0;
      
      MqlCalendarValue values[];
      datetime now = TimeCurrent();
      datetime start = now - 3600; // Look back 1 hour
      datetime end = now + 3600;   // Look forward 1 hour
      
      if(CalendarValueHistory(values, start, end))
      {
         for(int i=0; i<ArraySize(values); i++)
         {
            MqlCalendarEvent event;
            if(CalendarEventById(values[i].event_id, event))
            {
               int before = (event.importance == CALENDAR_IMPORTANCE_HIGH) ? m_highBefore : m_medBefore;
               int after = (event.importance == CALENDAR_IMPORTANCE_HIGH) ? m_highAfter : m_medAfter;
               
               if(event.importance == CALENDAR_IMPORTANCE_NONE || event.importance == CALENDAR_IMPORTANCE_LOW) continue;
               
               // Check if event is relevant (USD for XAUUSD)
               // Simple version: Block all High, and USD Medium
               if(event.importance == CALENDAR_IMPORTANCE_HIGH || event.importance == CALENDAR_IMPORTANCE_MODERATE)
               {
                  MqlCalendarCountry country;
                  if(CalendarCountryById(event.country_id, country))
                  {
                     // If moderate, only block if it's USD
                     if(event.importance == CALENDAR_IMPORTANCE_MODERATE && country.currency != "USD") continue;
                  }
                  
                  datetime eventTime = values[i].time;
                  if(now >= eventTime - before && now <= eventTime + after)
                  {
                     m_isBlackout = true;
                  }
                  
                  if(eventTime > now && (m_nextEventTime == 0 || eventTime < m_nextEventTime))
                  {
                     m_nextEventTime = eventTime;
                     m_nextEventName = event.name;
                  }
               }
            }
         }
      }
      return m_isBlackout;
   }

   string GetNextEventName() { return m_nextEventName; }
   datetime GetNextEventTime() { return m_nextEventTime; }
};

#endif
