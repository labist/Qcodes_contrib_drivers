###################
# This is an example of how we can use block capture for longer span
# By default, block capture returns at most 60 MHz span depending on the RBW
# In this example, we show that you can take longer span data by taking multiple
# spectra with different center frequencies and stitching them accordingly
# Does not work very good for certain resolution bandwidths, in that we see some jumps in data points
###################

#%%
import matplotlib.pyplot as plt
import numpy as np
from pyrf.devices.thinkrf import WSA
from pyrf.util import capture_spectrum
from time import time
# %%

RFE_MODE = 'SH' 
CENTER_FREQ = 6e9 #5.881e9 # - 100e6
SPP = 32*512
PPB = 1
RBW = 125e6 / (SPP * PPB * 2)  # 125 MHz is the sampling rate
## different factors give different bandwidth, 8 gives 40 MHz, 6 gives 60 MHz
AVERAGE = 10
DECIMATION = 1 # no decimation
ATTENUATION = 20
GAIN = 'HIGH'
TRIGGER_SETTING = {'type': 'NONE',
                'fstart': (CENTER_FREQ - 1e6), # some value
                'fstop': (CENTER_FREQ + 1e6),  # some value
                'amplitude': -100}
REFLEVEL = None

#%%
dut = WSA()

dut.connect('169.254.16.253')

# initialize RTSA configurations
dut.reset()
dut.request_read_perm()
dut.rfe_mode(RFE_MODE)
dut.freq(CENTER_FREQ)
dut.attenuator(ATTENUATION)
dut.psfm_gain(GAIN)
dut.trigger(TRIGGER_SETTING)
#%%
bw = 40e6
fstart = CENTER_FREQ - bw/2
fstop = CENTER_FREQ + bw/2

#%%

startT = time()
avglist = [1,5,10,50,100,500,1000,5000,10000]
timelist = []

spectrum = []
freqlist = []

stopf = 0

for avg in avglist:
    startT = time()
    while (stopf<fstop): # keep taking data until we have reached the stop frequency
        
        if (dut.freq() == CENTER_FREQ):
            startf_, stopf_, pow_data = capture_spectrum(dut, RBW, avg, DECIMATION)
            usableBW = stopf_-startf_
            nextfc = (fstart + (fstart + (usableBW)))/2. # update center frequency for next iteration
            dut.freq(nextfc) 

            continue
            
        dut.freq(nextfc) 

        startf, stopf, pow_data = capture_spectrum(dut, RBW, avg, DECIMATION)
        # print(startf/1e9, stopf/1e9, (stopf-startf)/1e9 )
        # print(len(pow_data))

        freqlist = np.concatenate( (np.linspace(startf,stopf,len(pow_data)), freqlist) )
        spectrum = np.concatenate( (pow_data, spectrum) )
        
        nextfstart = stopf # update start/stop frequencies for next iteration
        nextfstop = nextfstart + (stopf-startf)
        nextfc = (nextfstart + nextfstop)/2.
       # print(nextfstart/1e9,nextfstop/1e9)

    stopf = 0
    dut.freq(CENTER_FREQ)
    sortIdx = np.argsort(freqlist)
    spectrum = spectrum[sortIdx]
    freqlist = freqlist[sortIdx]

    stopT = time()
    print(f"Averages = {avg}, time = {stopT-startT:2.2f} sec")
    timelist.append(stopT-startT)

#%%
plt.plot(freqlist,spectrum)
# %%
freqlist[np.argmax(spectrum)]
# %%
