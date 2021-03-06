import os
from . import genproc
import numpy as np
import obspy

def newch(st,cfn,kploc=False):
    """
    :param    st: original traces
    :param   cfn: coefficients for conversion
    :param kploc: divide by location values---usually for 
                       remapping coupling coefficients
    :return  stn: new traces
    """
    # initialize new trace
    stn = obspy.Stream()

    # reference trace
    sti = st[0].copy()

    # change timing if necessary
    if len(sti.data)==1 and isinstance(cfn,obspy.Stream):
        cfi = cfn[0]
        ons = np.ones(cfi.data.shape,dtype=float)
        st = st.copy()
        for tr in st:
            tr.data = tr.data*ons
            tr.stats.starttime=cfi.stats.starttime
            tr.stats.delta=cfi.stats.delta

        # reference trace
        sti = st[0].copy()

    if isinstance(cfn,obspy.Stream):
        # merge coefficients in case
        cfn = cfn.merge()

        # keep track of channels used
        chn = []
        
        for tr in cfn:
            # times, relative to coefficient trace
            tim=(sti.stats.starttime-tr.stats.starttime)+sti.times()

            # times and data in coefficient trace
            tcf = tr.times()
            dcf = tr.data
            # check for nans
            iok = ~np.isnan(dcf)
            tcf,dcf=tcf[iok],dcf[iok]

            # interpolate through times
            if len(dcf)>1:
                cfi=interpolate.interp1d(tcf,dcf,bounds_error=None,kind='linear')
                cfi= cfi(tim)
            else:
                cfi=dcf[0]*np.ones(tim.shape)
                
            # before and after
            cfi[tim<=tcf[0]]=dcf[0]
            cfi[tim>=tcf[-1]]=dcf[-1]

            # identify the channels to multiply
            stmult=st.select(channel=tr.stats.location)
            
            for stm in stmult:
                # data here
                data=stm.data
            
                # multiply
                data = np.multiply(data,cfi)

                # identify the new channel to add to
                if kploc:
                    # keeping "location"---for mapping coupling matrices
                    stadd=stn.select(channel=tr.stats.channel,location=stm.stats.location)
                else:
                    # ignoring the "location"
                    stadd=stn.select(channel=tr.stats.channel)

                if len(stadd):
                    # add
                    stadd[0].data=stadd[0].data+data
                else:
                    # create new channel
                    sti.data = data
                    sti.stats.channel=tr.stats.channel
                    sti.stats.location=stm.stats.location
                    stn.append(sti.copy())
    else:
        # if the input is a dictionary of values
        for ch,cf in cfn.items():
            # start with no data
            data = 0.
            
            # add through coefficients
            for chi,cfi in cf.items():
                data = data + cfi * st.select(channel=chi)[0].data
                
            # modify trace
            sti.data = data
            sti.stats.channel = ch
                
            # add trace to new stream
            stn.append(sti.copy())

    # return the new set of traces
    return stn


def nonatm(X):
    """
    :return   cfn:     coefficients
        cfn['E+N-na'] is the set of coefficients to construct 'E+N-na'
    :return  cfst:     the same coefficients, but as a set of traces
    :return cfsto:     like cfst, but just a one to one mapping of the originals
    """
    # collect barometric response coefficients
    cf = np.array([])
    chn = np.array([],dtype=str)
    for ch in X.keys():
        cf = np.append(cf,X[ch]['atm'])
        chn = np.append(chn,ch)
    cf = cf.astype(float)

    # normalize
    cf = cf / np.dot(cf,cf)**0.5

    # initialize coefficients
    cfn,cfno = {},{}

    for k in range(0,len(cf)):
        # for each component, 
        # find a nearby component with little atmosphere
        cfi = -cf[k]*cf
        cfi[k] = 1+cfi[k]
        
        # normalize
        cfi = cfi / np.dot(cfi,cfi)**0.5
 
        # add to set
        cfn[chn[k]+'-na'] = dict(zip(chn,cfi))
        cfno[chn[k]] = dict(zip([chn[k]],[1]))

    # also create a set of traces, each with one value

    # initialize with default values
    cfst,cfsto=obspy.Stream(),obspy.Stream()
    tr=obspy.Trace()
    tr.stats.starttime=obspy.UTCDateTime('2000-01-01')
    tr.stats.delta=600
    
    for cfi in cfn:
        # channel to construct
        tr.stats.channel=cfi
        for cf in cfn[cfi]:
            # each coefficient
            tr.data = np.array([cfn[cfi][cf]])
            # channel to multiply
            tr.stats.location=cf
            # add to set
            cfst.append(tr.copy())

    for cfi in cfno:
        # channel to construct
        tr.stats.channel=cfi
        for cf in cfno[cfi]:
            # each coefficient
            tr.data = np.array([cfno[cfi][cf]])
            # channel to multiply
            tr.stats.location=cf
            # add to set
            cfsto.append(tr.copy())

    return cfn,cfst,cfsto

def ploticovbymonth(Xcfm):
    """
    :param     Xcfm: coefficients as a function of time
    """
    ky1=Xcfm.keys()
    ky2=Xcfm[ky1[0]].keys()

    from matplotlib import gridspec
    import matplotlib.pyplot as plt
    N=len(ky1)
    plt.close()
    f = plt.figure(figsize=(9,4*N))
    gs,p=gridspec.GridSpec(1,N),[]
    for gsi in gs:
        p.append(plt.subplot(gsi))
    p  = np.array(p)
    pm = p.reshape([N,1])
    gs.update(left=0.11,right=0.98)
    gs.update(bottom=0.07,top=0.98)
    gs.update(hspace=0.1,wspace=0.05)

    for k1 in range(0,N):
        h=[]
        for k2 in ky2:
            hh,=p[k1].plot(Xcfm[ky1[k1]][k2],marker='o',
                           linestyle='none')
            hh,=p[k1].plot(-Xcfm[ky1[k1]][k2],marker='o',
                           linestyle='none')

    

def icovbymonth(mdur=3,*args,**kwargs):
    """
    :param   mdur:  duration in months
    :param    as passed to idcovary
    """

    # interval centers
    nper=int(np.ceil(12./mdur)*3)
    mcent=np.arange(0,nper).astype(float)/nper*12+1.

    # initialize with everything
    Xcf,frc=idcovary(*args,**kwargs)

    Xcfm=Xcf.copy()
    for ky1 in Xcfm.keys():
        for ky2 in Xcfm[ky1].keys():
            Xcfm[ky1][ky2]=np.array([],dtype=float)

    for mc in mcent:
        # compute for each interval
        mnths=np.array([-.5,.5])*mdur+mc
        Xcfi,frc=idcovary(mnths=mnths,*args,**kwargs)

        for ky1 in Xcfm.keys():
            for ky2 in Xcfm[ky1].keys():
                Xcfm[ky1][ky2]=np.append(Xcfm[ky1][ky2],
                                         Xcfi[ky1][ky2])

    return Xcfm

def idcovary(st,chn=None,flm=None,starttime=None,endtime=None,
             mnths=[1,1]):
    """
    an SVD approach to identify a temporal signal common 
    to multiple components
    :param        st:  covariance
    :param       chn:  channels 
    :param       flm:  bandlimits
    :param starttime:  start time
    :param   endtime:  end time
    :param     mnths:  which months to use in the calculation
                          (default: [0,12])---all of them
    :return      Xcf:  coefficients for each one
    :return      frc:  fraction of signal on first component
    """

    if starttime is None:
        starttime = st[0].stats.starttime + 365.25 * 1.5 * 86400.
    if endtime is None:
        endtime = st[0].stats.endtime
    if flm is None:
        flm=np.array([1./5.,24./6.])/86400.
    if chn is None:
        # possible channels
        chpos = ['E+N','E-N','2EN','E+N-na','E-N-na','2EN-na',
                 'RS1','RS2','RS3','RS4']
        chn=np.array([],dtype=str)
        for tr in st:
            if tr.stats.channel in chpos:
                chn=np.append(chn,tr.stats.channel)
    M = len(chn)

    st=st.copy()
    # filter
    if flm[0]>0 or ~np.isinf(flm[1]):
        msk=genproc.prepfiltmask(st,tmask=10.*3600)
        st.filter('bandpass',freqmin=flm[0],freqmax=flm[1])
        genproc.addfiltmask(st,msk)
    st.trim(starttime=starttime,endtime=endtime)

    # number of points
    N = len(st.select(channel=chn[0])[0].data)

    # initialize
    mat = np.ndarray([N,M])
    iok = np.ones([N],dtype=bool)

    mnths=np.array(mnths)
    mnths1=mnths.astype(int)
    mnths2=mnths1+1
    wgt2=(mnths-mnths1).astype(float)
    mnths=np.mod(mnths-1,12)+1
    mnths1=np.mod(mnths1-1,12)+1
    mnths2=np.mod(mnths2-1,12)+1
    if mnths[0]!=mnths[1]:
        t1=np.min([tr.stats.starttime for tr in st])
        t2=np.max([tr.stats.endtime for tr in st])
        yrs=np.arange(t1.year,t2.year+1)
        t1b=np.array([obspy.UTCDateTime(yr,mnths1[0],1) 
                      for yr in yrs])
        t1a=np.array([obspy.UTCDateTime(yr,mnths2[0],1) 
                      for yr in yrs])
        if mnths[1]>mnths[0]:
            t2b=np.array([obspy.UTCDateTime(yr,mnths1[1],1) 
                          for yr in yrs])
            t2a=np.array([obspy.UTCDateTime(yr,mnths2[1],1) 
                          for yr in yrs])
        else:
            t2b=np.array([obspy.UTCDateTime(yr+1,mnths1[1],1) 
                          for yr in yrs])
            t2a=np.array([obspy.UTCDateTime(yr+1,mnths2[1],1) 
                          for yr in yrs])
        t1=t1b+(t1a-t1b)*wgt2[0]
        t2=t2b+(t2a-t2b)*wgt2[1]

    for k in range(0,M):
        # data
        sti1 = st.select(channel=chn[k])[0]
        mat[:,k] = sti1.data

        # choose a mask from observations
        if isinstance(sti1.data,np.ma.masked_array):
            iok = np.logical_and(~sti1.data.mask,iok)
            iok = np.logical_and(iok,~np.isnan(sti1.data.data))
        else:
            iok = np.logical_and(iok,~np.isnan(sti1.data))

    if mnths[0]!=mnths[1]:
        # time differences
        t1=t1-sti1.stats.starttime
        t2=t2-sti1.stats.starttime

        # look within this range only
        tm=sti1.times()
        i1=np.searchsorted(tm,t1)
        i2=np.searchsorted(tm,t2)
        tok=np.bincount(i1,minlength=tm.size+1)-\
            np.bincount(i2,minlength=tm.size+1)
        tok=np.cumsum(tok).astype(bool)[0:-1]

        iok=np.logical_and(iok,tok)

    # extract the portions of interest
    mat = mat[iok,:]

    # SVD
    U,S,V = np.linalg.svd(mat,full_matrices=False)
    
    # coefficients
    Xcf = {}
    Xcf['HCV-na'] = dict(zip(chn,V[0,:]))
    Xcf['LCV-na'] = dict(zip(chn,V[1,:]))

    # fraction of signal accounted for
    frc = S[0]/sum(S)

    # return coefficients and fraction
    return Xcf,frc


def writecf(stn,cfn,subdir=''):
    """
    write the estimated atmospheric coefficients to a file
    written to $DATA/STRAINPROC/ATMCF/subdir/atmcf_ stn
    :param    stn:   station---just for naming
    :param    cfn:   the coefficient dictionary
    :param subdir:   a subdirectory to write to 
                       (default:'', in main directory)
    """
    
    # directory
    fl = os.environ['STRAINPROC']
    fl = os.path.join(fl,'ATMCF',subdir)

    if not os.path.exists(fl):
        print('Creating directory '+fl)
        os.makedirs(fl)

    # file
    fl = os.path.join(fl,'atmcf_'+stn)
    fl = open(fl,'w')
    for ch in cfn.keys():
        fl.write(ch + ' : ')
        for chi in cfn[ch].keys():
            fl.write(' '+chi)
        fl.write('\n')
        for chi in cfn[ch].keys():
            fl.write(str(cfn[ch][chi]) + ' ')
        fl.write('\n')
    fl.close()

def readcf(stn,subdir=''):
    """ 
    read the estimated atmospheric coefficients from a file
    read from to $STRAINRPOC/ATMCF/atmcf_ stn
    :param   stn:  station
    :param subdir:   a subdirectory to write to 
                       (default:'', in main directory)
    :return  cfn:  estimated coefficients
    """

    cfn = {}

    fl = os.environ['STRAINPROC']
    fl = os.path.join(fl,'ATMCF',subdir,'atmcf_'+stn)

    if os.path.exists(fl):
        fl = open(fl,'r')
        for k in range(0,3):
            l1 = fl.readline().strip()
            l2 = fl.readline().strip()
            
            if l1:
                vls = l1.split(':')
                ch = vls[0].strip()
                ch2 = vls[1].strip().split(' ')
                cfni = l2.strip().split(' ')
                
                cfn[ch] = {}
                for m in range(0,len(ch2)):
                    cfn[ch][ch2[m]] = float(cfni[m])
        fl.close()
    else:
        print('Could not find coefficient file '+fl)


    return cfn

def multcf(cf1,cf2):
    """
    :param     cf1:  first coefficients, mapping X to Y
    :param     cf2:  second coefficients, mapping Y to Z
    :return     cf:  new coefficients
    """

    # identify components
    chY = cf1.keys()
    chX = cf1[chY[0]].keys()
    chZ = cf2.keys()
    chY = cf2[chZ[0]].keys()

    # initialize dictionary
    cfi = dict.fromkeys(chX,0.).copy()
    cf = {}
    for ch in chZ:
        cf[ch]=cfi.copy()

    for chj in chY:
        for chi in chX:
            for ch in chZ:
                cf[ch][chi]=cf[ch][chi]+cf1[chj][chi]*cf2[ch][chj]

    return cf


