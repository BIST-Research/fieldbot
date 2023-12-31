#include <Arduino.h>

#define TCC1_EMIT_RETRIGGER_EVENT_ID 0x19
#define TCC1_EMIT_STOP_EVENT_ID 0x1a

#define TCC2_WAIT_RETRIGGER_EVENT_ID 0x1f

#define ADC0_START_EVENT_ID 0x37

#define DMAC_CHANNEL_EVENT_BASE_ID 0x05
#define DMAC_RESULT_CHANNEL_EVENT_ID (DMAC_CHANNEL_EVENT_BASE_ID + DMAC_RESULT_CHANNEL)
#define DMAC_DSEQ_CHANNEL_EVENT_ID  (DMAC_CHANNEL_EVENT_BASE_ID + DMAC_DSEQ_CHANNEL)

#define START_EMIT_EVENT_CHANNEL 0x00
#define START_WAIT_EVENT_CHANNEL 0x01
#define START_LISTEN_EVENT_CHANNEL 0x02

#define NONE_EVENT_GENERATOR_ID 0x00

#define DMAC_GENERATOR_EVENT_BASE_ID 0x22
#define DMAC_EMIT_GENERATOR_EVENT_ID (DMAC_GENERATOR_EVENT_BASE_ID + DMAC_EMIT_MODULATOR_TIMER_CHANNEL)

#define TCC2_WAIT_OVERFLOW_EVENT_GENERATOR_ID 0x39
/*
void evsys_init(void){


  ML_SET_GCLK7_PCHCTRL(EVSYS_GCLK_ID_0);
  ML_SET_GCLK7_PCHCTRL(EVSYS_GCLK_ID_1);
  ML_SET_GCLK7_PCHCTRL(EVSYS_GCLK_ID_2);
  //SWTRIG --- TCC1_RETRIGGER --> async
  //DMA_TCC1 -- TCC1_STOP --> Async
  //DMA_TCC1 -- TCC2_RETRIGGER --> Async
  //TCC2_OVFEO -- DMA_ADC_DSEQ --> resync
  //TCC2_OVFEO -- DMA_ADC_RESULT --> resync

  TCC1->EVCTRL.reg = TCC_EVCTRL_EVACT1_STOP |
                     TCC_EVCTRL_EVACT0_RETRIGGER;

  EVSYS->USER[TCC1_EMIT_RETRIGGER_EVENT_ID].reg = EVSYS_USER_CHANNEL(START_EMIT_EVENT_CHANNEL + 1);
  EVSYS->USER[TCC1_EMIT_STOP_EVENT_ID].reg = EVSYS_USER_CHANNEL(START_WAIT_EVENT_CHANNEL + 1);

  TCC2->EVCTRL.reg = TCC_EVCTRL_EVACT0_RETRIGGER |
                     TCC_EVCTRL_OVFEO;

  EVSYS->USER[TCC2_WAIT_RETRIGGER_EVENT_ID].reg = EVSYS_USER_CHANNEL(START_WAIT_EVENT_CHANNEL + 1);

  DMAC->Channel[DMAC_RESULT_CHANNEL].CHEVCTRL.reg = DMAC_CHEVCTRL_EVIE |
                                                    DMAC_CHEVCTRL_EVACT_RESUME;

                            
  DMAC->Channel[DMAC_DSEQ_CHANNEL].CHEVCTRL.reg = DMAC_CHEVCTRL_EVIE |
                                                  DMAC_CHEVCTRL_EVACT_RESUME;

  EVSYS->USER[DMAC_RESULT_CHANNEL_EVENT_ID].reg = EVSYS_USER_CHANNEL(START_LISTEN_EVENT_CHANNEL + 1);
  EVSYS->USER[DMAC_DSEQ_CHANNEL_EVENT_ID].reg = EVSYS_USER_CHANNEL(START_LISTEN_EVENT_CHANNEL + 1);


  EVSYS->Channel[START_EMIT_EVENT_CHANNEL].CHANNEL.reg = EVSYS_CHANNEL_EDGSEL_NO_EVT_OUTPUT |
                                                         EVSYS_CHANNEL_PATH_ASYNCHRONOUS |
                                                         EVSYS_CHANNEL_EVGEN(NONE_EVENT_GENERATOR_ID);

  EVSYS->Channel[START_WAIT_EVENT_CHANNEL].CHANNEL.reg = EVSYS_CHANNEL_EDGSEL_NO_EVT_OUTPUT |
                                                         EVSYS_CHANNEL_PATH_ASYNCHRONOUS |
                                                         EVSYS_CHANNEL_EVGEN(DMAC_EMIT_GENERATOR_EVENT_ID);
 
  EVSYS->Channel[START_LISTEN_EVENT_CHANNEL].CHANNEL.reg = EVSYS_CHANNEL_EDGSEL_NO_EVT_OUTPUT |
                                                           EVSYS_CHANNEL_PATH_RESYNCHRONIZED |
                                                           EVSYS_CHANNEL_EVGEN(TCC2_WAIT_OVERFLOW_EVENT_GENERATOR_ID);                              
                                        
  // start TCC1
  //EVSYS->SWEVT.reg |= EVSYS_SWEVT_CHANNEL0;

  // stop TCC1
  //EVSYS->SWEVT.reg |= EVSYS_SWEVT_CHANNEL1;

}*/