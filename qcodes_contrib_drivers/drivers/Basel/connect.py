#%%
#!%load_ext autoreload
from DAC_SP1060 import SP1060
import numpy as np
import time

dac = SP1060('LNHR', 'TCPIP0::192.168.0.5::23::SOCKET', num_chans=12)

#%%
sleep_time = 0.02

dac.write('C WAV-B CLR') # Wave-Memory Clear.
time.sleep(sleep_time)
dac.write('C SWG MODE 0') # generate new Waveform.
time.sleep(sleep_time)
dac.write('C SWG WF ' + waveform) # set the waveform.
time.sleep(sleep_time)
dac.write('C SWG DF ' + frequency) # set frequency.
time.sleep(sleep_time)
dac.write('C SWG AMP ' + amplitude) # set the amplitude.
time.sleep(sleep_time)
dac.write('C SWG WMEM ' + wavemem) # set the Wave-Memory.
time.sleep(sleep_time)
dac.write('C SWG WFUN 0') # COPY to Wave-MEM -> Overwrite.
time.sleep(sleep_time)
dac.write('C SWG LIN ' + channel) # COPY to Wave-MEM -> Overwrite.
time.sleep(sleep_time)
dac.write('C AWG-' + memsave + ' CH ' + channel) # Write the Selected DAC-Channel for the AWG.
time.sleep(sleep_time)
dac.write('C SWG APPLY') # Apply Wave-Function to Wave-Memory Now.
time.sleep(sleep_time)
dac.write('C WAV-' + memsave + ' SAVE') # Save the selected Wave-Memory (WAV-A/B/C/D) to the internal volatile memory.
time.sleep(sleep_time)
dac.write('C WAV-' + memsave + ' WRITE') # Write the Wave-Memory (WAV-A/B/C/D) to the corresponding AWG-Memory (AWG-A/B/C/D).
time.sleep(0.5)
dac.write('C AWG-' + memsave + ' START') # Apply Wave-Function to Wave-Memory Now.

#%%
dac.awga.control('STOP')
dac.awga.wmclear('a')
dac.awga.wmclear('b')
dac.awga.wmclear('c')
dac.awga.wmclear('d')
dac.awga.mode('generate')
dac.awga.wave('sine')
dac.awga.freq(1.0)
dac.awga.amp(5.0)
dac.awga.selwavemem('a')
dac.awga.selfunc('copy')
dac.awga.lin('true')
dac.awga.selchan(12)
dac.ch12.status('ON')
dac.awga.apply()
dac.awga.wmsave('a')
dac.awga.wmtoawg('a')
#%%
dac.awga.control('STOP')
#%%
dac.awga.wmclear('a')
#%%
dac.awga.selchan()

#%%
dac.awga.control('START')
#%%
dac.awga.lin('true')

#%%
dac.awga.wmtoawg('a')

#%%
dac.awga.awgmem()

#%%
dac.awga.selchan(11)

#%%
dac.ch11.status('ON')
#%%
dac.awga.wmclear('a')

#%%
dac.write('C AWG-A STOP')

#%%
dac.ask("C AWG-A AP?")
#%%
dac.ask("C AWG-A AVA?")
#%%
dac.write('C AWG-A START')

#%%

dac.set_newWaveform(amplitude = '0.31', frequency = '13.7', wavemem='0')

#%%
#my commands in the dude's way in the precise order goddammit
dac.awga.control('STOP')
dac.awga.wmclear('a')
dac.awga.wmclear('b')
dac.awga.wmclear('c')
dac.awga.wmclear('d')
dac.awga.mode('generate')
dac.awga.wave('sine')
dac.awga.freq(1.0)
dac.awga.amp(5.0)
dac.awga.selwavemem('a')
dac.awga.selfunc('copy')
dac.awga.lin('true')
dac.awga.selchan(12)
dac.ch12.status('ON')
dac.awga.apply()
dac.awga.wmsave('a')
dac.awga.wmtoawg('a')
dac.awga.control('START')

#%% OLD STUFF BELOW HERE
# %%
#starting the awg
dac.ch12.status('ON')
dac.awga.wmclear('a')
dac.awga.wmclear('b')
dac.awga.wmclear('c')
dac.awga.wmclear('d')
dac.set_newWaveform()

#%%
#start the awg again with something

dac.set_newWaveform()

#%%
#clear memory and stop awg
dac.awga.wmclear('a')
dac.awga.wmclear('b')
dac.awga.wmclear('c')
dac.awga.wmclear('d')
dac.awga.control('STOP')
# %%
"""
other dude's process (?):
1. clear wave memory
2. set to generate a new waveform
3. sets values for that waveform (type, amplitude, etc)
4. selects wave memory and copies wavform to that
5. applies the wave function to the memory and then saves the wave memory to the volatile memory (S?)
6. writes wave memory to awg memory and applies the wave function to the wave memory
"""

#%%
dac.rampa.start(-3.0)
dac.rampa.stop(5.5)
dac.rampa.shape('sawtooth')
dac.rampa.selchan(12)
dac.rampa.period(7.6)
dac.rampa.cycles(3)
dac.rampa.mode('ramp')
dac.rampa.control('START')
#%%
dac.awga.selchan(12)
dac.awga.awgmem(1000)
dac.awga.cycles(0)
dac.awga.awgclock(1000)
dac.awga.mode('generate')
dac.awga.wave('sine')
dac.awga.freq(1.0)
dac.awga.clockset('adapt')
dac.awga.amp(5.0)
dac.awga.offset(1.0)
dac.awga.phase(0)
dac.awga.pulse(50)
dac.awga.control('START')
# %%
dac.awga.selwavemem('a')
dac.awga.selfunc('copy')
dac.awga.lin('true')
dac.awga.apply()
# %%
dac.awga.mode('saved')
dac.awga.wmsave('a')
dac.awga.wmtoawg('a')
dac.awga.control('START')
# %%
#other dude's code



# %%
dac.write('C WAV-A CLR')

# %%


# %%
#this block apparently works now for some reason unbeknownst to humanity
dac.awga.mode('generate')
dac.awga.wave('sine')
dac.awga.freq(1.0)
dac.awga.amp(5.0)
dac.awga.selchan(12)

dac.awga.control('START')

# %%
dac.awga.mode('generate')
dac.awga.wave('sine')
dac.awga.freq(1.0)
dac.awga.amp(5.0)
dac.awga.selchan(12)

dac.awga.selwavemem('a')
dac.awga.selfunc('copy')
dac.awga.lin('true')
dac.awga.apply()
dac.awga.wmsave('a')
dac.awga.wmtoawg('a')

dac.awga.control('START')
# %%
#replicating the miracle code?
dac.awgb.mode('generate')
dac.awgb.wave('sine')
dac.awgb.freq(10.0)
dac.awgb.amp(5.0)
dac.awgb.offset(2.0)
dac.awgb.selchan(5)

dac.awgb.control('START')
# %%
#this block also apparently works now for some reason unbeknownst to humanity
dac.awga.mode('generate')
dac.awga.wave('sine')
dac.awga.freq(1.0)
dac.awga.amp(3)
dac.awga.offset(2.0)
dac.awga.selchan(5)

dac.awga.control('START')
# %%
dac.awgb.mode('generate')
dac.awgb.wave('sine')
dac.awgb.freq(1.0)
dac.awgb.amp(5.0)
dac.awgb.selchan(5)

dac.awgb.selwavemem('a')
dac.awgb.selfunc('copy')
dac.awgb.lin('true')
dac.awgb.apply()
dac.awgb.wmsave('a')
dac.awgb.wmtoawg('a')

dac.awgb.control('START')
# %%
dac.awgb.mode('generate')
dac.awgb.wave('sine')
dac.awgb.freq(1.0)
dac.awgb.amp(5.0)
dac.awgb.selchan(5)

dac.awgb.selwavemem('a')
dac.awgb.selfunc('copy')
dac.awgb.lin('true')
dac.awgb.apply()
dac.awgb.wmsave('a')
dac.awgb.wmtoawg('a')

#dac.awgb.mode('saved')
dac.awgb.control('START')
# %%
#This time. THIS TIME FOR SURE
dac.awga.control('STOP')
dac.awga.wmclear('a')
dac.awga.wmclear('b')
dac.awga.wmclear('c')
dac.awga.wmclear('d')

dac.awga.awgmem(1000)

dac.awga.mode('generate')
dac.awga.wave('sine')
dac.awga.selwavemem('a')
dac.awga.selfunc('copy')
dac.awga.lin('true')
dac.awga.apply()
dac.awga.wmtoawg('a')
dac.awga.wmclear('a')

dac.awga.control('START')
# %%
