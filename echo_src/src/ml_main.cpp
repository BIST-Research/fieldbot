/*
 * Author: Ben Westcott
 * Date created: 8/10/22
 */

#include <ml_clocks.h>
#include <ml_port.h>
#include <ml_tcc_common.h>
#include <ml_tc_common.h>
#include <ml_dmac.h>
#include <ml_adc_common.h>
#include <ml_adc0.h>
#include <ml_adc1.h>
#include <ml_dac_common.h>
#include <ml_dac0.h>

//#define N_1ADC

#define N_ADC_SAMPLES 16000
#define N_DAC_TIMER 160
#define N_DAC_SAMPLES 3000
#define N_WAIT_TIMER 2

static uint16_t chirp_out_buffer[N_DAC_SAMPLES];

uint32_t init_chirp_buffer(void)
{
  bzero((void *)chirp_out_buffer, sizeof(uint16_t) * N_DAC_SAMPLES);
  return (uint32_t)&chirp_out_buffer[0] + N_DAC_SAMPLES * sizeof(uint16_t);
}

// DMAC looks for the base descriptor when serving a request
static DmacDescriptor base_descriptor[3] __attribute__((aligned(16)));
static volatile DmacDescriptor wb_descriptor[3] __attribute__((aligned(16)));

const uint32_t chirp_out_dmac_channel_settings = DMAC_CHCTRLA_BURSTLEN_SINGLE | //check when testing evsys
                                                 DMAC_CHCTRLA_TRIGACT_BURST |
                                                 //DMAC_CHCTRLA_TRIGSRC(DAC_DMAC_ID_EMPTY_0);
                                                 DMAC_CHCTRLA_TRIGSRC(TCC0_DMAC_ID_OVF);

const uint16_t chirp_out_dmac_descriptor_settings = DMAC_BTCTRL_VALID |
                                           //         DMAC_BTCTRL_EVOSEL_BURST | //check when testing evsys
                                                    DMAC_BTCTRL_BLOCKACT_BOTH | //check when testing evsys
                                                    DMAC_BTCTRL_BEATSIZE_HWORD |
                                                    DMAC_BTCTRL_SRCINC;

uint32_t chirp_out_source_address;

const ml_pin_settings dac_sample_timer_pin = {PORT_GRP_A, 21, PF_G, PP_ODD, OUTPUT_PULL_DOWN, DRIVE_OFF};
const ml_pin_settings wait_timer_pin = {PORT_GRP_A, 14, PF_F, PP_EVEN, OUTPUT_PULL_DOWN, DRIVE_OFF};
const ml_pin_settings state_timer_pin = {PORT_GRP_A, 16, PF_E, PP_EVEN, OUTPUT_PULL_DOWN, DRIVE_OFF};
const ml_pin_settings dac_pin = {PORT_GRP_A, 2, PF_B, PP_EVEN, ANALOG, DRIVE_ON};
const ml_pin_settings adc0_pin = {PORT_GRP_B, 9, PF_B, PP_ODD, ANALOG, DRIVE_OFF};
const ml_pin_settings adc1_pin = {PORT_GRP_B, 8, PF_B, PP_EVEN, ANALOG, DRIVE_OFF};

void dac_sample_timer_init(void)
{
  TCC_disable(TCC0);
  TCC_swrst(TCC0);

  TCC0->CTRLA.reg = 
  (
    //  TCC_CTRLA_PRESCALER_DIV2 |
      TCC_CTRLA_PRESCSYNC_PRESC
  );

  TCC0->WAVE.reg = TCC_WAVE_WAVEGEN_NFRQ;

  // 12 MHz / (2 * 6) = 1 MHz
  TCC_set_period(TCC0, 11);
  TCC_channel_capture_compare_set(TCC0, 1, 3);

  //peripheral_port_init(PORT_PMUX_PMUXE(PF_E), 7, OUTPUT_PULL_DOWN, DRIVE_ON);

  TCC_enable(TCC0);

  peripheral_port_init(&dac_sample_timer_pin);
}

void wait_timer_init(void)
{

  TCC_disable(TCC2);
  TCC_swrst(TCC2);
  //120Meg/512 = 468750
  TCC2->CTRLA.reg = TCC_CTRLA_PRESCALER_DIV1 | 
                    TCC_CTRLA_PRESCSYNC_PRESC;

  TCC2->WAVE.reg = TCC_WAVE_WAVEGEN_NFRQ | TCC_WAVE_POL0;

  TCC_set_period(TCC2, N_WAIT_TIMER);

  TCC_set_oneshot(TCC2);

  TCC_intenset(TCC2, TCC2_0_IRQn, TCC_INTENSET_OVF, 0);

  TCC2->CC[0].reg |= TCC_CC_CC(2);

  // GC port
  //perip2heral_port_init(PORT_PMUX_PMUXE(0x5), 28, OUTPUT_PULL_DOWN, DRIVE_ON);
  // D4 --> PA14 --> periph F
  peripheral_port_init(&wait_timer_pin);
}

inline void state_timer_retrigger(void)
{
  TC2->COUNT16.CTRLBSET.reg |= TC_CTRLBSET_CMD_RETRIGGER;
  while(TC2->COUNT16.SYNCBUSY.bit.CTRLB);
}

void state_timer_init(void)
{

  TC_disable(TC2);
  TC_swrst(TC2);

  // ((2**16 - 1) * 2)/120Meg = 1,09 ms
  TC2->COUNT16.CTRLA.reg = 
  (
    TC_CTRLA_PRESCALER_DIV2 |
    TC_CTRLA_MODE_COUNT16 |
    TC_CTRLA_PRESCSYNC_PRESC
  );

  TC2->COUNT16.WAVE.reg |= TC_WAVE_WAVEGEN_NFRQ;

  TC2->COUNT16.CTRLBSET.reg |= TC_CTRLBSET_ONESHOT;
  while(TC2->COUNT16.SYNCBUSY.bit.CTRLB);

  // (2**16)/2 = 32768
  TC2->COUNT16.CC[0].reg |= TC_COUNT16_CC_CC(32768);
  while(TC2->COUNT16.SYNCBUSY.bit.CC0);

  TC2->COUNT16.CTRLA.bit.ENABLE = 1;
  while(TC2->COUNT16.SYNCBUSY.bit.ENABLE);

  TC2->COUNT16.CTRLBSET.reg |= TC_CTRLBSET_CMD_STOP;
  while(TC2->COUNT16.SYNCBUSY.bit.CTRLB);

  // D7 --> PA18 --> periph E
  //peripheral_port_init_alt(PF_E, PP_EVEN, 7, OUTPUT_PULL_DOWN, DRIVE_ON);
  peripheral_port_init(&state_timer_pin);

}

#define DAC_DMAC_CHANNEL DMAC_CH2
#define DAC_DMAC_PRILVL PRILVL0

void dac_init(void)
{
  // Disable DAC
  DAC->CTRLA.bit.ENABLE = 0;
  DAC->CTRLA.bit.SWRST = 1;
  while (DAC->SYNCBUSY.bit.ENABLE || DAC->SYNCBUSY.bit.SWRST);

  // Use an external reference voltage (see errata; the internal reference is busted)
  DAC->CTRLB.reg = DAC_CTRLB_REFSEL_VREFPB;
  while (DAC->SYNCBUSY.bit.ENABLE || DAC->SYNCBUSY.bit.SWRST);

  DAC->DACCTRL[0].reg |= DAC_DACCTRL_CCTRL_CC12M;

  DAC->DACCTRL[0].bit.ENABLE = 1;
  while(DAC->SYNCBUSY.bit.ENABLE || DAC->SYNCBUSY.bit.SWRST);

  DMAC_channel_init
  (
    DAC_DMAC_CHANNEL,
    chirp_out_dmac_channel_settings,
    DAC_DMAC_PRILVL
  );


  //check when testing evsys
  DMAC_channel_intenset(DAC_DMAC_CHANNEL, DMAC_2_IRQn, DMAC_CHINTENSET_TCMPL, 0);

  DMAC_descriptor_init
  (
    chirp_out_dmac_descriptor_settings,
    N_DAC_SAMPLES,
    chirp_out_source_address,
    (uint32_t) &DAC->DATA[0].reg,
    (uint32_t) &base_descriptor[2],
    &base_descriptor[2]
  );

  peripheral_port_init(&dac_pin);
}

#define PASTE_FUSE(REG) ((*((uint32_t *) (REG##_ADDR)) & (REG##_Msk)) >> (REG##_Pos))

const uint32_t refbuf = PASTE_FUSE(ADC0_FUSES_BIASREFBUF);
const uint32_t r2r = PASTE_FUSE(ADC0_FUSES_BIASR2R);
const uint32_t comp = PASTE_FUSE(ADC0_FUSES_BIASCOMP);

const uint32_t adc0_dmac_channel_settings = 
(
  DMAC_CHCTRLA_TRIGACT_BURST |
  DMAC_CHCTRLA_TRIGSRC(ADC0_DMAC_ID_RESRDY)
);

const uint16_t adc0_dmac_descriptor_settings = 
(
  DMAC_BTCTRL_BEATSIZE_HWORD |
  DMAC_BTCTRL_DSTINC |
 // DMAC_BTCTRL_EVOSEL_BURST |
  DMAC_BTCTRL_BLOCKACT_BOTH |
  DMAC_BTCTRL_VALID
);

#define ADC0_DMAC_CHANNEL DMAC_CH0
#define ADC0_DMAC_PRILVL PRILVL0

uint16_t adc0_samples[N_ADC_SAMPLES];

void adc0_init(void)
{

  DMAC_channel_init
  (
    ADC0_DMAC_CHANNEL,
    adc0_dmac_channel_settings,
    ADC0_DMAC_PRILVL
  );

  DMAC_descriptor_init
  (
    adc0_dmac_descriptor_settings,
    N_ADC_SAMPLES,
    (uint32_t)&ADC0->RESULT.reg,
    (uint32_t)adc0_samples + sizeof(uint16_t) * N_ADC_SAMPLES,
    (uint32_t)&base_descriptor[ADC0_DMAC_CHANNEL],
    &base_descriptor[ADC0_DMAC_CHANNEL]
  );

  DMAC_channel_intenset
  (
    ADC0_DMAC_CHANNEL,
    DMAC_0_IRQn,
    DMAC_CHINTENSET_TCMPL,
    0
  );

  ADC0_init();

  peripheral_port_init(&adc0_pin);
}

const uint32_t adc1_dmac_channel_settings = 
(
  DMAC_CHCTRLA_TRIGACT_BURST |
  DMAC_CHCTRLA_TRIGSRC(ADC1_DMAC_ID_RESRDY)
);

const uint16_t adc1_dmac_descriptor_settings = 
(
  DMAC_BTCTRL_BEATSIZE_HWORD |
  DMAC_BTCTRL_DSTINC |
 // DMAC_BTCTRL_EVOSEL_BURST |
  DMAC_BTCTRL_BLOCKACT_BOTH |
  DMAC_BTCTRL_VALID
);

#define ADC1_DMAC_CHANNEL DMAC_CH1
#define ADC1_DMAC_PRILVL PRILVL0

uint16_t adc1_samples[N_ADC_SAMPLES];

void adc1_init(void)
{
  DMAC_channel_init
  (
    ADC1_DMAC_CHANNEL,
    adc1_dmac_channel_settings,
    ADC1_DMAC_PRILVL
  );

  DMAC_descriptor_init
  (
    adc1_dmac_descriptor_settings,
    N_ADC_SAMPLES,
    (uint32_t)&ADC1->RESULT.reg,
    (uint32_t)adc1_samples + sizeof(uint16_t) * N_ADC_SAMPLES,
    (uint32_t)&base_descriptor[ADC1_DMAC_CHANNEL],
    &base_descriptor[ADC1_DMAC_CHANNEL]
  );

  DMAC_channel_intenset
  (
    ADC1_DMAC_CHANNEL,
    DMAC_1_IRQn,
    DMAC_CHINTENSET_TCMPL,
    0
  );

  ADC1_init();

  peripheral_port_init(&adc1_pin);
}

typedef enum {IDLE, EMIT, WAIT, LISTEN} data_acquisition_state;
typedef enum {START_JOB = 0x10, AMP_STOP = 0xdd, AMP_START = 0xfe, GET_RUN_INFO = 0xfd, GET_CHIRP = 0x2f} host_command;
typedef enum {DO_CHIRP = 0x4f, DONT_CHIRP = 0x4e} run_info;

data_acquisition_state dstate = IDLE;

boolean do_emit_chirp = true;

const EPortType dp = g_APinDescription[7].ulPort;
const uint8_t dpin = g_APinDescription[7].ulPin;

#define SET_DPIN() (PORT->Group[dp].OUTSET.reg = (1 << PORT_OUTSET_OUTSET(dpin)))
#define UNSET_DPIN() (PORT->Group[dp].OUTCLR.reg = (1 << PORT_OUTCLR_OUTCLR(dpin)))

void setup(void) 
{
//#ifndef MODE_HARD_TRIG
  Serial.begin(115200);

//#endif
  chirp_out_source_address = init_chirp_buffer();
  //chirp_out_source_address = generate_chirp(80E3, 20E3);

  MCLK_init();
  GCLK_init();


  DMAC_init(&base_descriptor[0], &wb_descriptor[0]);

  dotstar_init();

  //emit_resonator_timer_init();

#ifdef MODE_HARD_TRIG

  state_timer_init();
  hardware_int_trigger_init();

#endif
  //emit_modulator_timer_init();
  dac_init();
  wait_timer_init();
  dac_sample_timer_init();
  DAC_enable();

  TCC_enable(TCC2);
  TCC_force_stop(TCC2);

  //job_led_toggle();

  adc0_init();
  adc1_init();

  //TCC_ENABLE(TCC0);
  //TCC_sync(TCC0);

  //TCC_ENABLE(TCC1);
  //TCC_sync(TCC1);

  //TCC_FORCE_STOP(TCC1);
  //TCC_sync(TCC1);
  
  ML_ADC_START(ADC0);
  ML_ADC_START(ADC1);

  ML_DMAC_ENABLE();
  ML_DMAC_CHANNEL_ENABLE(DAC_DMAC_CHANNEL);
  ML_DMAC_CHANNEL_SUSPEND(DAC_DMAC_CHANNEL);

  ML_DMAC_CHANNEL_ENABLE(ADC0_DMAC_CHANNEL);
  ML_DMAC_CHANNEL_SUSPEND(ADC0_DMAC_CHANNEL);

  ML_DMAC_CHANNEL_ENABLE(ADC1_DMAC_CHANNEL);
  ML_DMAC_CHANNEL_SUSPEND(ADC1_DMAC_CHANNEL);

}

boolean emit_start_intflag = false;
boolean emit_stop_intflag = false;
boolean wait_stop_intflag = false;
boolean adc0_done_intflag = false;
boolean adc1_done_intflag = false;

#define SERIAL_ACK 0x55
#define SERIAL_WRITE_ACK() (Serial.write(SERIAL_ACK))

void loop(void) 
{
  
  switch(dstate)
  {

    case IDLE: 
    {

      if(emit_start_intflag)
      {

        //TCC_FORCE_RETRIGGER(TCC1);
        //TCC_sync(TCC1);
        ML_DMAC_CHANNEL_RESUME(ADC0_DMAC_CHANNEL);
        ML_DMAC_CHANNEL_RESUME(ADC1_DMAC_CHANNEL);

        if(do_emit_chirp)
        {
          ML_DMAC_CHANNEL_RESUME(DAC_DMAC_CHANNEL);
        } else 
        {
          emit_stop_intflag=true;
        }


        dstate = EMIT;       

        emit_start_intflag = false;
      }
      
      break;  
    }

    case EMIT: 
    { 

      if(emit_stop_intflag)
      {

        //TCC_FORCE_STOP(TCC1);
        //TCC_sync(TCC1);

        TCC_force_retrigger(TCC2);
      
        dstate = WAIT;

        emit_stop_intflag = false;
      }
      
      break; 
    }

    case WAIT: 
    { 

      if(wait_stop_intflag)
      {

        //ML_DMAC_CHANNEL_RESUME(ADC0_DMAC_CHANNEL);
        //ML_DMAC_CHANNEL_RESUME(ADC1_DMAC_CHANNEL);

        dstate = LISTEN;

        wait_stop_intflag = false;

      }
      break;

    }

    case LISTEN: 
    {

      if(adc0_done_intflag & adc1_done_intflag)
      {

        adc0_done_intflag = adc1_done_intflag = false;

        uint16_t chunk_size = 2*N_ADC_SAMPLES/8;

        uint8_t *chunk_ptr0 = reinterpret_cast<uint8_t *>(&adc0_samples[0]);
        for(uint16_t i=0; i < 8; i++, chunk_ptr0 += chunk_size)
        {
          Serial.write(chunk_ptr0, sizeof(uint8_t) * chunk_size);
        }

#ifndef N_1ADC

        uint8_t *chunk_ptr1 = reinterpret_cast<uint8_t *>(&adc1_samples[0]);
        for(uint16_t i=0; i < 8; i++, chunk_ptr1 += chunk_size)
        {
          Serial.write(chunk_ptr1, sizeof(uint8_t) * chunk_size);
        }

#endif

        //TC2->COUNT16.CTRLBSET.reg |= TC_CTRLBSET_CMD_RETRIGGER;
        //while(TC2->COUNT16.SYNCBUSY.bit.CTRLB);
        dstate = IDLE;

      }
      break;

    }
  }

#ifndef MODE_HARD_TRIG

  if(Serial.available())
  {

    host_command opcode = (host_command)Serial.read();

    if(opcode <= START_JOB)
    {

      if(dstate == IDLE && opcode == START_JOB)
      {

        do_emit_chirp = (boolean)Serial.read();

        emit_start_intflag = true;

        //job_led_toggle();
        
      }
    }

    else if(opcode == AMP_STOP)
    {
      //SERIAL_WRITE_ACK();
    }

    else if(opcode == AMP_START)
    {
      //SERIAL_WRITE_ACK();
    }
    
    else if (opcode == GET_CHIRP)
    {

      char recv[2 * N_DAC_SAMPLES];
      Serial.readBytes(recv, 2 * N_DAC_SAMPLES);

      uint16_t *buf = reinterpret_cast<uint16_t *>(&recv[0]);
      
      for(int i=0; i < N_DAC_SAMPLES; i++)
      {
        chirp_out_buffer[i]  = buf[i];
      }
      
      //SERIAL_WRITE_ACK();

    }
  }
#endif

}

void DMAC_0_Handler(void)
{

  if(DMAC->Channel[ADC0_DMAC_CHANNEL].CHINTFLAG.bit.TCMPL)
  {
    ML_DMAC_CHANNEL_CLR_SUSP_INTFLAG(ADC0_DMAC_CHANNEL);
    DMAC->Channel[ADC0_DMAC_CHANNEL].CHINTFLAG.bit.TCMPL = 0x01;


    adc0_done_intflag = true;
  }

}

void DMAC_1_Handler(void)
{

  if(DMAC->Channel[ADC1_DMAC_CHANNEL].CHINTFLAG.bit.TCMPL)
  {

    ML_DMAC_CHANNEL_CLR_SUSP_INTFLAG(ADC1_DMAC_CHANNEL);
    DMAC->Channel[ADC1_DMAC_CHANNEL].CHINTFLAG.bit.TCMPL = 0x01;


    adc1_done_intflag = true;

  }

}


void DMAC_2_Handler(void)
{
  
  if(DMAC->Channel[DAC_DMAC_CHANNEL].CHINTFLAG.bit.TCMPL)
  {

    DOTSTAR_SET_BLUE();

    ML_DMAC_CHANNEL_CLR_SUSP_INTFLAG(DAC_DMAC_CHANNEL);
    DMAC->Channel[DAC_DMAC_CHANNEL].CHINTFLAG.bit.TCMPL = 0x01;

    emit_stop_intflag = true;
  }

}

void TCC2_0_Handler(void)
{

  if(TCC_IS_OVF(TCC2))
  {
    TCC_CLR_OVF_INTFLAG(TCC2);

    wait_stop_intflag = true;
  }
}

/*
void AC_Handler(void)
{
  
  static int ac_trig_cnt = 0;

  ML_AC_CLR_COMP0_INTFLAG();
  
  if(ac_trig_cnt != 0 && dstate == IDLE)
  {
      emit_start_intflag = true;
  } 
  
  ac_trig_cnt++;

}*/


