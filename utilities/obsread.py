from obspy import read
st = read("multifiles/sismic_records/*") 
print(st) 