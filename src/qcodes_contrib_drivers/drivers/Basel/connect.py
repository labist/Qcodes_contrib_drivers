#%%
from DAC_SP1060 import SP1060
import time 

dac = SP1060('LNHR', 'TCPIP0::192.168.0.5::23::SOCKET', num_chans=12, voltage_post_delay=0.01)
#dac.ch11.status('ON')

#%%
dac.ch1.volt(0)

# %%
dac.ch1.status('ON')
dac.ramphelper(start=0, stop=1, period=0.3, channel=1, cycles=2)

#%%
dac.ch1.status('OFF')
# %%
for c in dac.channels: c.status('OFF')
#%%
import random
for _ in range(3):
    for c in dac.channels:
        c.status('ON')
        time.sleep(0.02)
    for c in dac.channels:
        c.status('OFF')
        time.sleep(0.02)

while True:
    n = random.randint(0,11)
    c = dac.channels[n]
    if random.randint(0,1):
        c.status('ON')
    else:
        c.status('OFF')
    time.sleep(0.02)
#%%
import math
math.rand
#%%
dac.ch12.status('OFF')