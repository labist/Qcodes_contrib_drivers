#%%
#!%load_ext autoreload
from DAC_SP1060 import SP1060
import numpy as np
import time

dac = SP1060('LNHR', 'TCPIP0::192.168.0.5::23::SOCKET', num_chans=12)
dac.ch11.status('ON')
#%%
#my code blocks
sleep_time = 0.2
# Generating a waveform via SWG #
dac.swg.mode('generate')
time.sleep(sleep_time)
dac.swg.wave('sine')
time.sleep(sleep_time)
dac.swg.freq(17.8)
time.sleep(sleep_time)
dac.swg.amp(1.3)
time.sleep(sleep_time)
#%%
# Saving an SWG generated waveform to AWG memory to use #
dac.swg.selwm('a')
time.sleep(sleep_time)
dac.swg.selfunc('copy')
# linearization here. channel should have already been selected at this point

time.sleep(sleep_time)
dac.swg.apply(1)
time.sleep(sleep_time)
dac.wma.toawg(1)
time.sleep(sleep_time)
#%%
# Double check memories to ensure saving went well #
dac.swg.size() # Size of waveform via the first step
dac.wma.memsize() # Memory size of WAV-A. Should match your swg generated memory
dac.awga.memsize() # Memory size of AWG-A. Should match your swg generated memory
#%%
# Setting an AWG to run via a waveform in its memory #
dac.awga.selchan(12)
time.sleep(sleep_time)
dac.ch12.status('ON')
time.sleep(0.5)
dac.awga.control('START')
time.sleep(sleep_time)
#%%



#%%
sleep_time = 0.2
channel = '11'
waveform = '0'
frequency = np.random.rand()*100+20
amplitude = np.random.rand()*1+0.5
print(f'Frequency {frequency:.3f} Hz, Amp {amplitude/np.sqrt(2):.3f} Vrms')
amplitude = str(amplitude)
frequency = str(frequency)
wavemem = '0'
memsave = 'A'

dac.write('C WAV-A CLR') # Wave-Memory Clear.
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
dac.write('C SWG LIN 0') # linearization. nobody knows what this does
time.sleep(sleep_time)
dac.write('C AWG-' + memsave + ' CH ' + channel) # set the DAC-Channel for the AWG.
time.sleep(sleep_time)
dac.write('C SWG APPLY') # Apply Wave-Function to Wave-Memory Now.
time.sleep(sleep_time)
# dac.write('C WAV-' + memsave + ' SAVE') # Save the selected Wave-Memory (WAV-A/B/C/D) to the internal volatile memory.
# time.sleep(sleep_time)
dac.write('C WAV-' + memsave + ' WRITE') # Write the Wave-Memory (WAV-A/B/C/D) to the corresponding AWG-Memory (AWG-A/B/C/D).
time.sleep(0.3)
dac.write('C AWG-' + memsave + ' START') # start awg

#%%
dac.ask('C SWG DF?')
#%%
dac.ask('C SWG WMEM?') # set the Wave-Memory.
#%%
dac.write('C SWG WMEM 0') # set the Wave-Memory.

#%%
0.436/float(amplitude)
#%%
dac.ask('C SWG LIN?')
#%%
vpp = dac.ask('C SWG AMP?')
vpp, float(vpp)/np.sqrt(2)
#%% stop the awg. set the frequency. apply wavefunction to wave memory. write wave memory to awg memory. start the awg
sleep_time = 0.2
freq = np.random.rand()*100+3
print('Setting awg frequency to', freq, ' Hz')

dac.write('C AWG-A STOP')
time.sleep(sleep_time)

dac.write(f'C SWG DF {freq}')
time.sleep(sleep_time)

#%%
dac.write('C SWG APPLY') 
time.sleep(sleep_time)

#%%
dac.write('C WAV-A WRITE') # Write the Wave-Memory to awg memory
time.sleep(sleep_time)

#%%
dac.write('C AWG-A START')
time.sleep(sleep_time)

print(dac.awga.awgmem())

#%%
dac.write('C AWG-' + memsave + ' STOP') # Apply Wave-Function to Wave-Memory Now.
#%%
dac.write('C AWG-' + memsave + ' START') # Apply Wave-Function to Wave-Memory Now.

#%% 
dac.ask('C SWG MODE?')

#%% change amplitude
dac.write('C SWG DF 15')
#%%
dac.awga.awgmem()

#%%
dac.write('C SWG APPLY') # apply wavefunction to wave memory
#%%
dac.write('C WAV-A WRITE') # Write the Wave-Memory (WAV-A/B/C/D) to the corresponding AWG-Memory (AWG-A/B/C/D).
#%%
#%%
