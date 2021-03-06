#!/usr/bin/env python2.7
# 
# 
# Last update:
#     20170302 numpy.sqrt()*background_sigma
#     20170308 (1) we find that the image pixel rms underestimates the flux error, as there are some background variation across images like ACS, so we decide to multiply a factor of 2 to the background_sigma. 
#              (2) for down-weighting the offset/Separation with the extended-parameter, we should only apply when image S/N > 3. And the way we calculate the extended-parameter changed from S/N_(largest_ellipse) / S/N_(smallest_ellipse) to S/N_(largest ellp. S/N>2) / S/N_(smallest ellip. S/N>2). 
#              (3) fixed "== numpy.nan" thing. Because "numpy.nan == numpy.nan" is False, if a value is nan, it does not equal to itself. 
#              (4) output "Source.Photometry['ALMA S/N']" to the output text file.
#              (5) measure peak pixel position within each ellipse -- this needs to modify "caap_python_lib_image.py" "elliptical_Photometry"
# 

try:
    import pkg_resources
except ImportError:
    raise SystemExit("Error! Failed to import pkg_resources!")

pkg_resources.require("numpy")
pkg_resources.require("astropy>=1.3")
pkg_resources.require("matplotlib")
pkg_resources.require("wcsaxes") # http://wcsaxes.readthedocs.io/en/latest/getting_started.html

import os
import sys
import re
import glob
import inspect
import math
import numpy
import astropy
from astropy import units
from astropy.io import fits
from astropy.wcs import WCS
import wcsaxes
from pprint import pprint


from caap_python_lib_highz import *
from caap_python_lib_image import *
from caap_python_lib_telescopes import *


try: 
    import matplotlib
except ImportError:
    raise SystemExit("Error! Failed to import matplotlib!")

import platform
if platform.system() == 'Darwin':
    matplotlib.use('Qt5Agg')
else:
    matplotlib.use('TkAgg')

try: 
    from matplotlib import pyplot
except ImportError:
    raise SystemExit("Error! Failed to import pyplot from matplotlib!")

try: 
    from matplotlib.colors import hex2color, rgb2hex
except ImportError:
    raise SystemExit("Error! Failed to import hex2color, rgb2hex from matplotlib.colors!")

try:
    from matplotlib.patches import Ellipse, Circle, Rectangle
except ImportError:
    raise SystemExit("Error! Failed to import Ellipse, Circle, Rectangle from matplotlib.patches!")

try: 
    from astropy.visualization import astropy_mpl_style
except ImportError:
    raise SystemExit("Error! Failed to import astropy_mpl_style from astropy.visualization!")

try:
    from astropy.visualization import MinMaxInterval, PercentileInterval, AsymmetricPercentileInterval, SqrtStretch, PowerStretch, ImageNormalize
except ImportError:
    raise SystemExit("Error! Failed to import MinMaxInterval, PercentileInterval, AsymmetricPercentileInterval, SqrtStretch, PowerStretch, ImageNormalize from astropy.visualization!")
# ImageNormalize requires astropy>=1.3

try: 
    import scipy
    import skimage
    from skimage.exposure import rescale_intensity
    from skimage.feature import peak_local_max
    #from skimage.morphology import is_local_maximum
except ImportError:
    raise SystemExit("Error! Failed to import skimage (scikit-image) or scipy!")

try:
    from itertools import groupby
    from operator import itemgetter
except ImportError:
    raise SystemExit("Error! Failed to import groupby from itertools!")

try:
    from copy import copy
except ImportError:
    raise SystemExit("Error! Failed to import copy from copy!")
    # this is for copying data structure, otherwise 

try:
    import shutil
except ImportError:
    raise SystemExit("Error! Failed to import shutil!")
    # for copying file with metadata

try:
    from datetime import datetime
except ImportError:
    raise SystemExit("Error! Failed to import datetime!")








#pyplot.rcParams['font.family'] = 'NGC'
pyplot.rcParams['font.size'] = 13
pyplot.rcParams['axes.labelsize'] = 'large'
#pyplot.rcParams['axes.labelpad'] = 5.0
#pyplot.rcParams['ytick.major.pad'] = 10 # padding between ticks and axis
pyplot.rcParams['xtick.minor.visible'] = True # 
pyplot.rcParams['ytick.minor.visible'] = True # 
pyplot.rcParams['figure.figsize'] = 20, 18
pyplot.style.use(astropy_mpl_style)


# stretch_sqrt = SqrtStretch()
# Image2 = stretch_sqrt(Image)

# from matplotlib.colors import LogNorm
# pyplot.imshow(image_data, cmap='gray', norm=LogNorm())













# 
class Logger(object):
    # "Lumberjack class - duplicates sys.stdout to a log file and it's okay"
    # source: http://stackoverflow.com/q/616645
    # see -- http://stackoverflow.com/questions/616645/how-do-i-duplicate-sys-stdout-to-a-log-file-in-python/2216517#2216517
    # usage:
    #    Log=Logger('Sleeps_all.night')
    #    print('works all day')
    #    Log.close()
    # 
    def __init__(self, filename="Logger.log", mode="a", buff=0):
        self.stdout = sys.stdout
        self.file = open(filename, mode, buff)
        sys.stdout = self
    
    def __del__(self):
        self.close()
    
    def __enter__(self):
        pass
    
    def __exit__(self, *args):
        self.close()
    
    def write(self, message):
        self.stdout.write(message)
        self.file.write(message)
    
    def flush(self):
        self.stdout.flush()
        self.file.flush()
        os.fsync(self.file.fileno())
    
    def close(self):
        if self.stdout != None:
            sys.stdout = self.stdout
            self.stdout = None
        
        if self.file != None:
            self.file.close()
            self.file = None









# 
class CrossMatch_Identifier(object):
    # 
    def __init__(self, Source=Highz_Galaxy(), RefSource=Highz_Galaxy(), FitsImageFile="", FitsImageWavelength=0.0, FitsImageFrequency=0.0):
        self.Source = Source
        self.RefSource = RefSource
        self.FitsImageFile = ""
        self.FitsImageWavelength = 0.0
        self.FitsImageFrequency = 0.0
        self.FitsImageData = []
        self.FitsImageHeader = []
        self.FitsImageWCS = WCS()
        self.FitsImagePixScale = [0.0, 0.0]
        self.Match = {
            'Morphology': {
                'SepDist': 0.0, 
                'SepAngle': 0.0, 
                'Score': 0.0, 
                'Extended': 0.0, 
                'Polyfit': [], 
            }, 
            'Photometry': {
                'Aperture': [], 
                'Flux': 0.0, 
                'FluxError': 0.0, 
                'FluxBias': 0.0, 
                'S/N': 0.0, 
                'GrowthCurve': [], 
                'Score': 0.0, 
            }, 
            'Score': 0.0
        }
        # 
        self.World = {}
        # 
        if type(FitsImageFile) is list:
            if len(FitsImageFile)>0:
                self.FitsImageFile = FitsImageFile[0]
            else:
                print("Error! Input FitsImageFile is empty!")
                sys.exit()
        else:
            self.FitsImageFile = str(FitsImageFile)
        # 
        if self.FitsImageFile.find('*')>=0:
            FindImageFile = glob.glob(self.FitsImageFile)
            if len(FindImageFile)>0:
                self.FitsImageFile = FindImageFile[0]
            else:
                print("Error! Find no FitsImageFile according to the input \"%s\"!"%(self.FitsImageFile))
                sys.exit()
        # 
        self.FitsImageWavelength = FitsImageWavelength
        self.FitsImageFrequency = FitsImageFrequency
        # 
        # check FitsImageFile
        if not os.path.isfile(self.FitsImageFile):
            print("Error! \"%s\" was not found!\n"%(self.FitsImageFile))
            sys.exit()
        # 
        # read FitsImageData
        self.FitsImageStruct = fits.open(self.FitsImageFile)
        #print self.FitsImageStruct.info()
        for ExtId in range(len(self.FitsImageStruct)):
            if type(self.FitsImageStruct[ExtId]) is astropy.io.fits.hdu.image.PrimaryHDU:
                self.FitsImageData = self.FitsImageStruct[ExtId].data
                self.FitsImageHeader = self.FitsImageStruct[ExtId].header
                # fix NAXIS to 2 if NAXIS>2, this is useful for VLA images
                if(self.FitsImageHeader['NAXIS']>2):
                    while(self.FitsImageHeader['NAXIS']>2):
                        self.FitsImageData = self.FitsImageData[0]
                        for TempStr in ('NAXIS','CTYPE','CRVAL','CRPIX','CDELT','CUNIT','CROTA'):
                            TempKey = '%s%d'%(TempStr,self.FitsImageHeader['NAXIS'])
                            if TempKey in self.FitsImageHeader:
                                del self.FitsImageHeader[TempKey]
                                #print("del %s"%(TempKey))
                        for TempInt in range(long(self.FitsImageHeader['NAXIS'])):
                            TempKey = 'PC%02d_%02d'%(TempInt+1,self.FitsImageHeader['NAXIS'])
                            if TempKey in self.FitsImageHeader:
                                del self.FitsImageHeader[TempKey]
                                #print("del %s"%(TempKey))
                            TempKey = 'PC%02d_%02d'%(self.FitsImageHeader['NAXIS'],TempInt+1)
                            if TempKey in self.FitsImageHeader:
                                del self.FitsImageHeader[TempKey]
                                #print("del %s"%(TempKey))
                        self.FitsImageHeader['NAXIS'] = self.FitsImageHeader['NAXIS']-1
                    #print(self.FitsImageData.shape)
                    #print(self.FitsImageHeader['NAXIS'])
                    #sys.exit()
                for TempStr in ('NAXIS','CTYPE','CRVAL','CRPIX','CDELT','CUNIT','CROTA'):
                    for TempInt in (3,4):
                        TempKey = '%s%d'%(TempStr,TempInt)
                        if TempKey in self.FitsImageHeader:
                            del self.FitsImageHeader[TempKey]
                # 
                self.FitsImageWCS = WCS(self.FitsImageHeader)
                self.FitsImagePixScale = astropy.wcs.utils.proj_plane_pixel_scales(self.FitsImageWCS) * 3600.0 # arcsec
                # we take the first image <TODO> extension number
                break
    # 
    def about(self):
        # 
        # get my name 
        # -- see http://stackoverflow.com/questions/1690400/getting-an-instance-name-inside-class-init
        self.World['My Name'] = ""
        self.World['My Names'] = []
        tmp_frame = inspect.currentframe().f_back
        tmp_variables = dict(tmp_frame.f_globals.items() + tmp_frame.f_locals.items())
        for tmp_name, tmp_variable in tmp_variables.items():
            if isinstance(tmp_variable, self.__class__):
                if hash(self) == hash(tmp_variable):
                    self.World['My Names'].append(tmp_name)
        if len(self.World['My Names']) > 0:
            self.World['My Name'] = self.World['My Names'][0]
        # 
        # print crossmatcher info
        tmp_str_max_length = 0
        if tmp_str_max_length < len(self.World['My Name']+' '):
            tmp_str_max_length = len(self.World['My Name']+' ')
        tmp_str_source = self.Source.Field+'--'+self.Source.Name+'--'+str(self.Source.SubID)
        if tmp_str_max_length < len(self.FitsImageFile):
            tmp_str_max_length = len(self.FitsImageFile)
        if tmp_str_max_length < len(tmp_str_source):
            tmp_str_max_length = len(tmp_str_source)
        tmp_str_format_fixedwidth = '{0:<%d}'%(tmp_str_max_length)
        tmp_str_format_filleddash = '{0:-<%d}'%(tmp_str_max_length)
        print("")
        print(' |---------------- %s-|'%( tmp_str_format_filleddash.format(self.World['My Name']+' ')         ))
        print(' |        Source | %s |'%( tmp_str_format_fixedwidth.format(tmp_str_source)                    ))
        print(' | FitsImageFile | %s |'%( tmp_str_format_fixedwidth.format(self.FitsImageFile)                ))
        print(' |-----------------%s-|'%( tmp_str_format_filleddash.format('-')                               ))
        print("")
    # 
    def match_morphology(self, OutputDir='results', OutputName='', Overwrite=False, FoV=15.0):
        if len(self.FitsImageData)>0 and self.Source and self.RefSource:
            # 
            # check output directory
            if not os.path.isdir(OutputDir):
                os.mkdir(OutputDir)
            # 
            # check Source data structure
            if not self.Source.Field:
                print("Error! \"Source\" does not have \"Field\" info!")
                return
            if not self.Source.Name:
                print("Error! \"Source\" does not have \"Name\" info!")
                return
            #if not self.Source.ID:
            #    print("Error! \"Source\" does not have \"ID\" info!")
            #    return
            if not self.Source.SubID:
                print("Error! \"Source\" does not have \"SubID\" info!")
                return
            if not 'Major Axis' in self.Source.Morphology:
                print("Error! \"Source.Morphology\" does not have \"Major Axis\" info!")
                return
            if not 'Minor Axis' in self.Source.Morphology:
                print("Error! \"Source.Morphology\" does not have \"Minor Axis\" info!")
                return
            if not 'Pos Angle' in self.Source.Morphology:
                print("Error! \"Source.Morphology\" does not have \"Pos Angle\" info!")
                return
            # 
            # check FitsImageFile
            if len(self.FitsImageFile) == 0:
                print("Error! \"FitsImageFile\" does not have valid content!")
                return
            # 
            # recognize Instrument and Telescope from the fits image file name
            StrInstrument, StrTelescope = recognize_Instrument(self.FitsImageFile)
            if len(StrInstrument) == 0 or len(StrTelescope) == 0:
                print("Error! Failed to recognize Instrument and Telescope info from the input fits image file name: \"%s\"!"%(self.FitsImageFile))
                pyplot.pause(3.0)
                return
            # 
            # prepare output figure and text file names
            if OutputName == '':
                OutputName = self.Source.Field+'--'+str(self.Source.Name)+'--'+str(self.Source.SubID)
            PlotOutput = OutputDir+'/'+OutputName+'--'+StrTelescope+'--'+StrInstrument.replace(' ','-')+'.pdf'
            TextOutput = OutputDir+'/'+OutputName+'--'+StrTelescope+'--'+StrInstrument.replace(' ','-')+'.txt'
            LoggOutput = OutputDir+'/'+OutputName+'--'+StrTelescope+'--'+StrInstrument.replace(' ','-')+'.log'
            LockOutput = OutputDir+'/'+OutputName+'--'+StrTelescope+'--'+StrInstrument.replace(' ','-')+'.lock' #<TODO># 
            # 
            # begin Logger
            temp_Logger = Logger(LoggOutput, mode='w')
            # 
            # check previous crossmatch results
            if os.path.isfile(TextOutput):
                # 
                # <20170224> added a check step to make sure our scores do not have nan
                with open(TextOutput, 'r') as fp:
                    temp_Score_Total = numpy.nan
                    temp_Score_Morph = numpy.nan
                    temp_Score_Photo = numpy.nan
                    temp_Score_Exten = numpy.nan
                    for lp in fp:
                        #<DEBUG># if lp.find('=') >= 0:
                        #<DEBUG>#     print(lp) #<TODO># print debug info
                        if lp.startswith('Match.Score'):
                            temp_Score_Total = (lp.split('=')[1]).split('#')[0]
                        elif lp.startswith('Match.Morphology.Score'):
                            temp_Score_Morph = (lp.split('=')[1]).split('#')[0]
                        elif lp.startswith('Match.Photometry.Score'):
                            temp_Score_Photo = (lp.split('=')[1]).split('#')[0]
                        elif lp.startswith('Match.Morphology.Extended'):
                            temp_Score_Exten = (lp.split('=')[1]).split('#')[0]
                    fp.close()
                    #print(float(temp_Score_Total))
                    #print(float(temp_Score_Morph))
                    #print(float(temp_Score_Photo))
                    #print(float(temp_Score_Exten))
                    if math.isnan(float(temp_Score_Total)) or \
                       math.isnan(float(temp_Score_Morph)) or \
                       math.isnan(float(temp_Score_Photo)) or \
                       math.isnan(float(temp_Score_Exten)) :
                        print("Warning! Previous crossmatching result \"%s\" contains \"nan\"! Will redo the crossmatching due to NaN values found!"%(TextOutput))
                        Overwrite = True
                        pyplot.pause(2.0)
                #if(TextOutput.find('22721')>=0):
                #    pyplot.pause(2.0)
                if not Overwrite:
                    print("Found previous crossmatching result: \"%s\"! Will not redo the crossmatching unless the \"overwrite\" option are input!"%(TextOutput))
                    return
            # 
            # do morphology check
            if True:
                # 
                # draw the source as an Ellipse
                posxy = self.FitsImageWCS.wcs_world2pix(self.Source.RA, self.Source.Dec, 1) # 3rd arg: origin is the coordinate in the upper left corner of the image. In FITS and Fortran standards, this is 1. In Numpy and C standards this is 0.
                major = self.Source.Morphology['Major Axis'] / self.FitsImagePixScale[0] # in unit of pixel
                minor = self.Source.Morphology['Minor Axis'] / self.FitsImagePixScale[1] # in unit of pixel
                angle = self.Source.Morphology['Pos Angle']
                ellip = Ellipse(xy=posxy, width=major, height=minor, angle=angle, edgecolor='green', facecolor="none", linewidth=2, zorder=10)
                #PlotPanel.add_artist(ellip)
                print("Plotting Cutouts image \"%s\""%(self.FitsImageFile))
                print("Plotting Source as %s"%(ellip))
                # 
                # zoom the image to a zoomsize of 15 arcsec
                #zoomFoV = 15.0 # 0.0 # 15.0 #<TODO># FoV Field of View
                zoomFoV = float(FoV)
                #<DEBUG>#zoomFoV = 0.0
                if(zoomFoV>0.0):
                    zoomsize = zoomFoV / self.FitsImagePixScale # zoomsize in pixel unit corresponding to 7 arcsec
                    zoomrect = (numpy.round([posxy[0]-(zoomsize[0]/2.0), posxy[0]+(zoomsize[0]/2.0), posxy[1]-(zoomsize[1]/2.0), posxy[1]+(zoomsize[1]/2.0)]).astype(long))
                    print("Zooming to FoV %.3f arcsec around source position %.3f %.3f with zoomrect %s"%(zoomFoV, posxy[0], posxy[1], zoomrect))
                    zoomimage, zoomwcs = crop(self.FitsImageData, zoomrect, imagewcs = self.FitsImageWCS)
                    zoomscale = numpy.divide(numpy.array(zoomimage.shape, dtype=float), numpy.array(self.FitsImageData.shape, dtype=float))
                    zoomposxy = numpy.subtract(posxy, [zoomrect[0],zoomrect[2]])
                    zoomellip = Ellipse(xy=zoomposxy, width=major, height=minor, angle=angle, edgecolor=hex2color('#00CC00'), facecolor="none", linewidth=2, zorder=10)
                else:
                    zoomsize = numpy.array(self.FitsImageData.shape)
                    zoomrect = numpy.array([1, self.FitsImageData.shape[0], 1, self.FitsImageData.shape[1]])
                    zoomimage = self.FitsImageData
                    zoomwcs = self.FitsImageWCS
                    zoomscale = numpy.array([1.0, 1.0])
                    zoomposxy = numpy.array(posxy)
                    zoomellip = ellip
                # 
                # add a double-size ellip
                zoomellip_large = copy(zoomellip)
                zoomellip_large.set_linewidth(1.25)
                zoomellip_large.width = zoomellip_large.width * 2.00
                zoomellip_large.height = zoomellip_large.height * 2.00
                # 
                # add a half-size ellip
                zoomellip_small = copy(zoomellip)
                zoomellip_small.set_linewidth(1.25)
                zoomellip_small.width = zoomellip_small.width * 0.25
                zoomellip_small.height = zoomellip_small.height * 0.25
                # 
                # add a blank-position ellip
                #print(zoomellip.__dict__)
                blankellip = copy(zoomellip)
                blankellip.center = blankellip.center + numpy.array(zoomimage.shape) * numpy.array([-0.22,+0.22]) # 0.22 is an arbitrary number to put the blank-position ellipse
                blankellip.set_edgecolor(hex2color('#FFFFFF'))
                # 
                # add a double-size ellip
                blankellip_large = copy(blankellip)
                blankellip_large.set_linewidth(1.25)
                blankellip_large.width = blankellip_large.width * 2.00
                blankellip_large.height = blankellip_large.height * 2.00
                # 
                # add a half-size ellip
                blankellip_small = copy(blankellip)
                blankellip_small.set_linewidth(1.25)
                blankellip_small.width = blankellip_small.width * 0.25
                blankellip_small.height = blankellip_small.height * 0.25
                # 
                # 
                # Plot fits image
                print('Showing FitsImage')
                PlotDevice = pyplot.figure()
                PlotPanel = PlotDevice.add_axes([0.10, 0.10, 0.85, 0.85], projection = zoomwcs) # plot RA Dec axes #  PlotPanel = PlotDevice.add_subplot(1,1,1)
                PlotPanel.grid(False)
                PlotPanel.coords[0].set_major_formatter('hh:mm:ss.ss')
                PlotPanel.coords[1].set_major_formatter('dd:mm:ss.s')
                PlotPanel.coords[0].set_ticks_visible(True)
                PlotPanel.coords[1].set_ticks_visible(True)
                PlotPanel.coords[0].display_minor_ticks(True)
                PlotPanel.coords[1].display_minor_ticks(True)
                PlotPanel.coords[0].set_minor_frequency(10)
                PlotPanel.coords[1].set_minor_frequency(10)
                PlotPanel.set_xlabel('RA')
                PlotPanel.set_ylabel('Dec')
                # 
                #normfactor = ImageNormalize(self.FitsImageData, interval=AsymmetricPercentileInterval(5,99.5)) # , stretch=SqrtStretch()
                #PlotImage = PlotPanel.imshow(self.FitsImageData, origin='lower', cmap='binary', norm=normfactor, aspect='equal') # cmap='gray' # cmap='jet' # cmap='binary'
                ##PlotDevice.colorbar(PlotImage)
                # 
                normfactor = ImageNormalize(zoomimage, interval=AsymmetricPercentileInterval(19.5,99.5))
                # 
                PlotImage = PlotPanel.imshow(zoomimage, origin='lower', cmap='binary', norm=normfactor, aspect='equal')
                #PlotDevice.colorbar(PlotImage)
                # 
                # add the ellipse(s)
                PlotPanel.add_artist(blankellip_large)
                PlotPanel.add_artist(blankellip_small)
                PlotPanel.add_artist(blankellip)
                PlotPanel.add_artist(zoomellip_large)
                PlotPanel.add_artist(zoomellip_small)
                PlotPanel.add_artist(zoomellip)
                print("Plotting Source as %s in the zoomed image with zoomscale=[%s] and zoomsize=[%s]"%(zoomellip,','.join(zoomscale.astype(str)),','.join(zoomsize.astype(str))))
                # 
                # add annotation at top-left
                PlotPanel.annotate(StrTelescope+' '+StrInstrument, fontsize=15, color=hex2color('#00CC00'), 
                                   xy=(0.03, 0.95), xycoords='axes fraction', 
                                   bbox = dict(boxstyle="round,pad=0.2", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='left', verticalalignment='center')
                PlotPanel.annotate('FoV %.1f arcsec'%(zoomFoV), 
                                   xy=(0.03, 0.95-0.06), xycoords='axes fraction', color=hex2color('#00CC00'), fontsize=14, 
                                   bbox = dict(boxstyle="round,pad=0.2", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='left', verticalalignment='center')
                # 
                # add annotation at top-right
                PlotPanel.annotate(self.Source.Field+': '+str(self.Source.Name)+': '+str(self.Source.SubID), fontsize=15, color=hex2color('#00CC00'), 
                                   xy=(0.97, 0.95), xycoords='axes fraction', 
                                   bbox = dict(boxstyle="round,pad=0.2", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                # 
                # draw the RefSource by a red cross symbol
                refposxy = zoomwcs.wcs_world2pix(self.RefSource.RA, self.RefSource.Dec, 1)
                #refposxy = numpy.subtract(refposxy, [zoomrect[0],zoomrect[2]])
                refposxy = numpy.array(refposxy)
                PlotPanel.autoscale(False)
                PlotPanel.plot([refposxy[0]], [refposxy[1]], marker='+', markeredgewidth=1.85, 
                               markersize=numpy.mean(0.06*PlotDevice.get_size_inches()*PlotDevice.dpi), 
                               color=hex2color('#CC0000'), zorder=9)
                print("Plotting RefSource at [%s] in the zoomed image with zoomscale=[%s] and zoomsize=[%s]"%(','.join(refposxy.astype(str)),','.join(zoomscale.astype(str)),','.join(zoomsize.astype(str))))
                # 
                # add annotation
                for refname in self.RefSource.Names.keys():
                    PlotPanel.annotate(refname+': '+str(self.RefSource.Names.get(refname)), fontsize=15, color=hex2color('#CC0000'), 
                                   xy=(0.97, 0.95-0.06), xycoords='axes fraction', 
                                   bbox = dict(boxstyle="round,pad=0.2", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                # 
                # calc Separation
                SepXY = (refposxy - zoomposxy) * self.FitsImagePixScale
                SepDist = math.sqrt( numpy.sum((SepXY)**2) ) # in arcsec
                SepAngle = numpy.arctan2(SepXY[1], SepXY[0]) / math.pi * 180.0
                PosAngle = self.Source.Morphology['Pos Angle']
                print("RefSource to Source has a SepDist=%.3f [arcsec] and SepAngle=%.1f [degree], comparing to Source Morphology PosAngle=%.1f [degree]."%(SepDist,SepAngle,self.Source.Morphology['Pos Angle']))
                # 
                # add annotation
                PlotPanel.annotate("SepDist = %.3f [arcsec]"%(SepDist), 
                                   xy=(0.97, 0.95-0.075-0.045*1), xycoords='axes fraction', color=hex2color('#CC0000'), fontsize=13, 
                                   bbox = dict(boxstyle="round,pad=0.1", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                PlotPanel.annotate("SepAngle = %.1f [deg]"%(SepAngle), 
                                   xy=(0.97, 0.95-0.075-0.045*2), xycoords='axes fraction', color=hex2color('#CC0000'), fontsize=13, 
                                   bbox = dict(boxstyle="round,pad=0.1", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                PlotPanel.annotate("PosAngle = %.1f [deg]"%(self.Source.Morphology['Pos Angle']), 
                                   xy=(0.97, 0.95-0.075-0.045*3), xycoords='axes fraction', color=hex2color('#00CC00'), fontsize=13, 
                                   bbox = dict(boxstyle="round,pad=0.1", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                # 
                # 
                # 
                # draw the image
                pyplot.grid(False)
                pyplot.draw()
                pyplot.pause(0.15)
                # 
                # 
                # 
                # check the source to be extended or not -- by doing aperture photometry
                print("")
                print("Photometrying...")
                print("")
                PhotAper_Range = numpy.array(range(1,10)) * 0.25 # x0.25 to x2.25 FWHM
                PhotAper_Array = []
                for PhotAper_Value in PhotAper_Range:
                    tempellip = copy(zoomellip)
                    tempellip.width = tempellip.width*PhotAper_Value
                    tempellip.height = tempellip.height*PhotAper_Value
                    tempflux, tempnpix, tempcpix = elliptical_Photometry(zoomimage, tempellip, imagewcs=zoomwcs)
                    PhotAper_Array.append({'Radius':PhotAper_Value, 'Shape':tempellip, 
                                           'Cpix':tempcpix, 
                                           'Npix':tempnpix, 'Fint':tempflux, 'Fbkg':numpy.nan, 
                                           'Flux':numpy.nan, 'Error':numpy.nan, 'S.B.':numpy.nan, 
                                           'S.B. Annulus':numpy.nan, 'S.B. Growth':numpy.nan, 'Flux Growth':numpy.nan, 
                                           'S/N':numpy.nan, 'S/N Annulus':numpy.nan})
                    print("Integrated source-position flux within %0.2fxFWHM is %g (weighted central pixel %.3f %.3f)"%(PhotAper_Value, tempflux, tempcpix[0], tempcpix[1]))
                # 
                # do another photometry at a blank position for testing
                print("")
                BlankAper_Range = PhotAper_Range
                BlankAper_Array = []
                for BlankAper_Value in BlankAper_Range:
                    tempellip = copy(blankellip)
                    tempellip.width = tempellip.width*BlankAper_Value
                    tempellip.height = tempellip.height*BlankAper_Value
                    tempflux, tempnpix, tempcpix = elliptical_Photometry(zoomimage, tempellip)
                    BlankAper_Array.append({'Radius':BlankAper_Value, 'Shape':tempellip, 
                                            'Cpix':tempcpix, 
                                            'Npix':tempnpix, 'Fint':tempflux, 'Fbkg':numpy.nan, 
                                            'Flux':numpy.nan, 'Error':numpy.nan, 'S.B.':numpy.nan, 
                                            'S.B. Annulus':numpy.nan, 'S.B. Growth':numpy.nan, 'Flux Growth':numpy.nan, 
                                            'S/N':numpy.nan, 'S/N Annulus':numpy.nan})
                    print("Integrated blank-position flux within %0.2fxFWHM is %g"%(BlankAper_Value, tempflux))
                # 
                # calc background by "caap_analyze_fits_image_pixel_histogram.py"
                print("")
                print("Calculating background...")
                if not os.path.isfile(self.FitsImageFile+'.pixel.statistics.txt'):
                    os.system('%s "%s"'%('caap_analyze_fits_image_pixel_histogram.py', self.FitsImageFile))
                background_flux = numpy.nan
                background_sigma = numpy.nan
                with open(self.FitsImageFile+'.pixel.statistics.txt', 'r') as fp:
                    for lp in fp:
                        if lp.startswith('Gaussian_mu'):
                            background_flux = float((lp.split('=')[1]).split('#')[0].replace(' ',''))
                        elif lp.startswith('Gaussian_sigma'):
                            background_sigma = float((lp.split('=')[1]).split('#')[0].replace(' ',''))
                # 
                # <20170224> added a check step to make sure we measure the FitGauss
                if background_sigma is numpy.nan or background_sigma < 0:
                    os.system('%s "%s"'%('caap_analyze_fits_image_pixel_histogram.py', self.FitsImageFile))
                    with open(self.FitsImageFile+'.pixel.statistics.txt', 'r') as fp:
                        for lp in fp:
                            if lp.startswith('Gaussian_mu'):
                                background_flux = float((lp.split('=')[1]).split('#')[0].replace(' ',''))
                            elif lp.startswith('Gaussian_sigma'):
                                background_sigma = float((lp.split('=')[1]).split('#')[0].replace(' ',''))
                # 
                # apply a factor of 2 to the background sigma because of the background variation <20170308><dzliu><plang>
                background_sigma = background_sigma * 2.0
                # 
                # print background flux (sigma)
                print("Median background flux is %g"%(background_flux))
                print("StdDev of the background is %g"%(background_sigma))
                # 
                # calc background-subtracted net flux
                print("")
                print("Calculating background-subtracted flux...")
                print("")
                for iAper in range(len(BlankAper_Array)):
                    BlankAper_Array[iAper]['Fbkg'] = background_flux * BlankAper_Array[iAper]['Npix']
                    BlankAper_Array[iAper]['Flux'] = BlankAper_Array[iAper]['Fint'] - BlankAper_Array[iAper]['Fbkg']
                    BlankAper_Array[iAper]['Error'] = background_sigma * numpy.sqrt(BlankAper_Array[iAper]['Npix'])
                    BlankAper_Array[iAper]['S.B.'] = BlankAper_Array[iAper]['Flux'] / BlankAper_Array[iAper]['Npix'] # flux per pixel area surface brightness
                    BlankAper_Array[iAper]['S/N'] = BlankAper_Array[iAper]['Flux'] / BlankAper_Array[iAper]['Error']
                    # compare with previous aperture photometry to get growth
                    if iAper == 0:
                        BlankAper_Array[iAper]['S/N Annulus'] = BlankAper_Array[iAper]['S/N']
                        BlankAper_Array[iAper]['S.B. Annulus'] = BlankAper_Array[iAper]['S.B.']
                        BlankAper_Array[iAper]['S.B. Growth'] = 1.0 # surface brightness growth
                        BlankAper_Array[iAper]['Flux Growth'] = 1.0 # absolute flux growth
                    else:
                        iPrev = iAper-1
                        BlankAper_Array[iAper]['S/N Annulus'] = (BlankAper_Array[iAper]['Flux']-BlankAper_Array[iPrev]['Flux']) / (background_sigma * numpy.sqrt(BlankAper_Array[iAper]['Npix']-BlankAper_Array[iPrev]['Npix']))
                        BlankAper_Array[iAper]['S.B. Annulus'] = (BlankAper_Array[iAper]['Flux']-BlankAper_Array[iPrev]['Flux']) / (BlankAper_Array[iAper]['Npix']-BlankAper_Array[iPrev]['Npix'])
                        BlankAper_Array[iAper]['S.B. Growth'] = BlankAper_Array[iAper]['S.B.'] / BlankAper_Array[iPrev]['S.B.'] # surface brightness growth
                        BlankAper_Array[iAper]['Flux Growth'] = BlankAper_Array[iAper]['Flux'] / BlankAper_Array[iPrev]['Flux'] # absolute flux growth
                    print("Background-subtracted blank-position  flux within %.2fxFWHM is %-10.4g (S/N:%7.4g) (flux growth:%6.3g) (S.B. growth:%6.3g)"%(BlankAper_Array[iAper]['Radius'], BlankAper_Array[iAper]['Flux'], BlankAper_Array[iAper]['Flux']/BlankAper_Array[iAper]['Error'], BlankAper_Array[iAper]['Flux Growth'], BlankAper_Array[iAper]['S.B. Growth']))
                print("")
                for iAper in range(len(PhotAper_Array)):
                    PhotAper_Array[iAper]['Fbkg'] = background_flux * PhotAper_Array[iAper]['Npix']
                    PhotAper_Array[iAper]['Flux'] = PhotAper_Array[iAper]['Fint'] - PhotAper_Array[iAper]['Fbkg']
                    PhotAper_Array[iAper]['Error'] = background_sigma * numpy.sqrt(PhotAper_Array[iAper]['Npix'])
                    PhotAper_Array[iAper]['S.B.'] = PhotAper_Array[iAper]['Flux'] / PhotAper_Array[iAper]['Npix'] # flux per pixel area surface brightness
                    PhotAper_Array[iAper]['S/N'] = PhotAper_Array[iAper]['Flux'] / PhotAper_Array[iAper]['Error']
                    # compare with previous aperture photometry to get growth
                    if iAper == 0:
                        PhotAper_Array[iAper]['S/N Annulus'] = PhotAper_Array[iAper]['S/N']
                        PhotAper_Array[iAper]['S.B. Annulus'] = PhotAper_Array[iAper]['S.B.']
                        PhotAper_Array[iAper]['S.B. Growth'] = 1.0 # surface brightness growth
                        PhotAper_Array[iAper]['Flux Growth'] = 1.0 # absolute flux growth
                    else:
                        iPrev = iAper-1
                        PhotAper_Array[iAper]['S/N Annulus'] = (PhotAper_Array[iAper]['Flux']-PhotAper_Array[iPrev]['Flux']) / (background_sigma * numpy.sqrt(PhotAper_Array[iAper]['Npix']-PhotAper_Array[iPrev]['Npix']))
                        PhotAper_Array[iAper]['S.B. Annulus'] = (PhotAper_Array[iAper]['Flux']-PhotAper_Array[iPrev]['Flux']) / (PhotAper_Array[iAper]['Npix']-PhotAper_Array[iPrev]['Npix'])
                        PhotAper_Array[iAper]['S.B. Growth'] = PhotAper_Array[iAper]['S.B.'] / PhotAper_Array[iPrev]['S.B.'] # surface brightness growth
                        PhotAper_Array[iAper]['Flux Growth'] = PhotAper_Array[iAper]['Flux'] / PhotAper_Array[iPrev]['Flux'] # absolute flux growth
                    print("Background-subtracted source-position flux within %.2fxFWHM is %-10.4g (S/N:%7.4g) (flux growth:%6.3g) (S.B.:%10.4g) (S.B. annulus:%10.4g) (S/N annulus:%7.4g)"%(PhotAper_Array[iAper]['Radius'], PhotAper_Array[iAper]['Flux'], PhotAper_Array[iAper]['Flux']/PhotAper_Array[iAper]['Error'], PhotAper_Array[iAper]['Flux Growth'], PhotAper_Array[iAper]['S.B.'], PhotAper_Array[iAper]['S.B. Annulus'], PhotAper_Array[iAper]['S/N Annulus']))
                # 
                # poly fit to the S.B. radial profile
                temp_index_x1FWHM = 3 # [0.25, 0.50, 0.75, 1.00], 1.00 is the subscript 3
                temp_x = [t['Radius'] for t in PhotAper_Array]
                temp_y = [t['S/N Annulus'] for t in PhotAper_Array]
                temp_x = temp_x
                temp_y = temp_y / temp_y[temp_index_x1FWHM] - 1.0# temp_y[temp_index_x1FWHM] is x1.00 FHWM
                self.Match['Morphology']['Polyfit'] = numpy.polyfit(temp_x[temp_index_x1FWHM:], temp_y[temp_index_x1FWHM:], 1) #<TODO># use 1-order polyfit, i.e. a line
                #
                # estimate extended parameter
                # -- try to use 'S.B. Annulus' profile polyfit
                #self.Match['Morphology']['Extended'] = 10.0**(self.Match['Morphology']['Polyfit'][0]) * 100
                # -- try to use 'S/N Annulus' (outer S/N excess)
                #self.Match['Morphology']['Extended'] = numpy.sum(temp_y[3:])
                # -- try to use just final and first 'S.B'
                #self.Match['Morphology']['Extended'] = PhotAper_Array[-1]['S.B.'] / PhotAper_Array[0]['S.B.'] * 100.0
                # -- try to use the final and first 'S.B' where 'S/N' > 2 -- <20170308><dzliu><plang> 
                temp_r = [ t['Radius']       for t in PhotAper_Array if(t['S/N']>=2.0)]
                temp_s = [ t['S.B. Annulus'] for t in PhotAper_Array if(t['S/N']>=2.0)]
                if len(temp_s) <= 1: 
                    #temp_s = [numpy.nan]
                    self.Match['Morphology']['Extended'] = 0.0
                else:
                    #self.Match['Morphology']['Extended'] = temp_s[-1] / temp_s[0] * 100.0
                    self.Match['Morphology']['Extended'] = temp_s[-1] / temp_s[0] / (temp_r[-1]-temp_r[0]) * 100.0
                print("")
                print('Radial annulus polyfit: %s'%(temp_x))
                print('Radial annulus polyfit: %s'%(temp_y))
                print('Radial annulus polyfit: %s'%(self.Match['Morphology']['Polyfit']))
                print('Radial annulus excess: %s'%(numpy.sum(temp_y)))
                print('Radial annulus final/first ratio: %s'%(PhotAper_Array[-1]['S.B.'] / PhotAper_Array[0]['S.B.']))
                # 
                # choose the highest S/N as the result
                #temp_f = [t['Flux'] for t in PhotAper_Array]
                #temp_df = [t['Error'] for t in PhotAper_Array]
                #temp_snr = numpy.array(temp_f)/numpy.array(temp_df)
                #temp_index = numpy.where(temp_snr == numpy.max(temp_snr))
                #self.Match['Photometry']['Flux'] = PhotAper_Array[temp_index[0][0]]['Flux']
                #self.Match['Photometry']['FluxError'] = PhotAper_Array[temp_index[0][0]]['Error']
                #self.Match['Photometry']['Aperture'] = PhotAper_Array[temp_index[0][0]]['Radius']
                #self.Match['Photometry']['S/N'] = self.Match['Photometry']['Flux'] / self.Match['Photometry']['FluxError']
                # 
                # choose the x1.00 FHWM S/N as the result
                temp_index_x1FWHM = 3 # [0.25, 0.50, 0.75, 1.00], 1.00 is the subscript 3
                self.Match['Photometry']['Flux'] = PhotAper_Array[temp_index_x1FWHM]['Flux']
                self.Match['Photometry']['FluxError'] = PhotAper_Array[temp_index_x1FWHM]['Error']
                self.Match['Photometry']['Aperture'] = PhotAper_Array[temp_index_x1FWHM]['Radius']
                self.Match['Photometry']['S/N'] = self.Match['Photometry']['Flux'] / self.Match['Photometry']['FluxError']
                for iAper in range(len(PhotAper_Array)):
                    self.Match['Photometry']['GrowthCurve'].append((PhotAper_Array[iAper]['Radius']*major*numpy.mean(self.FitsImagePixScale), PhotAper_Array[iAper]['S.B. Annulus'])) # tuple, radisu in unit of arcsec, flux and flux error in original pixel value unit. 
                # 
                # 
                #<20170304><dzliu><plang># down-weight the offset so as to improve the score
                offset_down_weighting = 1.0
                if self.Match['Morphology']['Extended'] > 0 and self.Match['Morphology']['Extended'] == self.Match['Morphology']['Extended']:
                    if self.Match['Photometry']['S/N'] >= 5.0:
                        offset_down_weighting = numpy.min([numpy.max([self.Match['Morphology']['Extended']/100.0, 1.0]), 3.0]) # -- <20170308> only down-weight if source image S/N>5.0
                # 
                # 
                # 
                # 
                # 
                # 
                # 
                # calc match quality -- get a score
                self.Match['Morphology']['SepDist'] = SepDist # value ranges from 0 to Major Axis and more
                self.Match['Morphology']['SepAngle'] = numpy.min([numpy.abs(SepAngle-PosAngle),numpy.abs(SepAngle-PosAngle-360),numpy.abs(SepAngle-PosAngle+360)]) # value ranges from 0 to 180.0
                self.Match['Morphology']['Score'] = 100.0 * \
                                                    ( 1.0 - 
                                                      1.0 * (
                                                        self.Match['Morphology']['SepDist'] / offset_down_weighting / (
                                                          numpy.abs(self.Source.Morphology['Major Axis']*numpy.cos(numpy.deg2rad(self.Match['Morphology']['SepAngle']))) + 
                                                          numpy.abs(self.Source.Morphology['Minor Axis']*numpy.sin(numpy.deg2rad(self.Match['Morphology']['SepAngle'])))
                                                        )
                                                      )
                                                    )
                                                    # Separation projected relative to a*cos(theta) + b*sin(theta)
                                                    # 50% means that the SepDist equals the radius of the ellipse at that SepAngle. 
                                                    # 
                self.Match['Morphology']['Score'] = numpy.max([self.Match['Morphology']['Score'], 0])
                self.Match['Morphology']['Score'] = numpy.min([self.Match['Morphology']['Score'], 100])
                # 
                #<test># self.Match['Photometry']['Score'] = ( 1.0 - numpy.exp( -(self.Match['Photometry']['S/N']/12.0                 ) ) ) * 50.0 
                #<test>#                                   + ( 1.0 - numpy.exp( -(self.Source.Photometry['ALMA Band 6 240 GHz S/N']/6.0) ) ) * 50.0
                # 
                #self.Match['Photometry']['Score'] = ( 0.4 * numpy.min([self.Match['Photometry']['S/N']/15.0, 0.5]) + 
                #                                      0.6 * numpy.min([self.Source.Photometry['ALMA Band 6 240 GHz S/N']/15.0, 0.5])
                #                                    ) * 100.0
                #                                    # it means: ALMA S/N ~6 = 100%
                #                                    #           image S/N ~6 -> ~10 = 100% [x] <TODO><20170310>
                # 
                #<20170313>#self.Match['Photometry']['Score'] = numpy.sqrt( ( self.Match['Photometry']['S/N'] )**2 + 
                #<20170313>#                                                ( self.Source.Photometry['ALMA Band 6 240 GHz S/N'] )**2 )
                #<20170313>#self.Match['Photometry']['Score'] = numpy.min( [self.Match['Photometry']['Score']/10.0, 1.0] ) * 100.0
                #<20170313>#                                    # it means: ALMA and image quadratic S/N ~10 = score 100
                # 
                #self.Match['Photometry']['Score'] = ( 0.5 * self.Match['Photometry']['S/N']/15.0 + 
                #                                      0.5 * self.Source.Photometry['ALMA Band 6 240 GHz S/N']/15.0
                #                                    ) * 100.0
                # 
                self.Match['Photometry']['Score'] = ( 0.25 * numpy.min( [ self.Match['Photometry']['S/N']/15.0, 2.0 ] ) + 
                                                      0.75 * numpy.min( [ self.Source.Photometry['ALMA Band 6 240 GHz S/N']/12.0, 2.0 ] )
                                                    ) * 100.0
                # 
                # 
                # 
                # 
                self.Match['Score'] = ( 0.5 * self.Match['Morphology']['Score'] + 
                                        0.5 * self.Match['Photometry']['Score'] )
                # 
                # 
                # 
                # 
                # 
                # plot annotation
                PlotPanel.annotate("M. Score = %.1f [%%]"%(self.Match['Morphology']['Score']), 
                                   xy=(0.97, 0.95-0.075-0.045*4), xycoords='axes fraction', color=hex2color('#00CC00'), fontsize=13, 
                                   bbox = dict(boxstyle="round,pad=0.1", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                # 
                # plot annotation
                PlotPanel.annotate("Extended = %.1f [%%]"%(self.Match['Morphology']['Extended']), 
                                   xy=(0.97, 0.95-0.075-0.045*5), xycoords='axes fraction', color=hex2color('#00CC00'), fontsize=13, 
                                   bbox = dict(boxstyle="round,pad=0.1", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                # 
                # plot annotation
                PlotPanel.annotate("Downweight = %.0f [%%]"%(offset_down_weighting*100), 
                                   xy=(0.97, 0.95-0.075-0.045*6), xycoords='axes fraction', color=hex2color('#00CC00'), fontsize=13, 
                                   bbox = dict(boxstyle="round,pad=0.1", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                # 
                # plot annotation
                PlotPanel.annotate("Image S/N = %.3f"%(self.Match['Photometry']['S/N']), 
                                   xy=(0.97, 0.95-0.075-0.045*7), xycoords='axes fraction', color=hex2color('#00CC00'), fontsize=13, 
                                   bbox = dict(boxstyle="round,pad=0.1", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                # 
                # plot annotation
                PlotPanel.annotate("ALMA S/N = %.3f"%(self.Source.Photometry['ALMA Band 6 240 GHz S/N']), 
                                   xy=(0.97, 0.95-0.075-0.045*8), xycoords='axes fraction', color=hex2color('#00CC00'), fontsize=13, 
                                   bbox = dict(boxstyle="round,pad=0.1", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                # 
                # plot annotation
                PlotPanel.annotate("P. Score = %.1f [%%]"%(self.Match['Photometry']['Score']), 
                                   xy=(0.97, 0.95-0.075-0.045*9), xycoords='axes fraction', color=hex2color('#00CC00'), fontsize=13, 
                                   bbox = dict(boxstyle="round,pad=0.1", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                # 
                # plot annotation
                PlotPanel.annotate("Score = %.1f [%%]"%(self.Match['Score']), 
                                   xy=(0.97, 0.95-0.075-0.045*10), xycoords='axes fraction', color=hex2color('#00CC00'), fontsize=13, 
                                   bbox = dict(boxstyle="round,pad=0.1", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                # 
                # plot annotation
                PlotPanel.annotate("zp = %.3f"%(self.Source.Redshifts['Laigle 2015 photo-z']), 
                                   xy=(0.97, 0.95-0.075-0.045*11), xycoords='axes fraction', color=hex2color('#CC0000'), fontsize=13, 
                                   bbox = dict(boxstyle="round,pad=0.1", alpha=0.6, facecolor=hex2color('#FFFFFF'), edgecolor=hex2color('#FFFFFF'), linewidth=2), 
                                   horizontalalignment='right', verticalalignment='center')
                # 
                # show the image
                pyplot.draw()
                pyplot.pause(0.20)
                #print("Click anywhere on the figure to continue")
                #pyplot.waitforbuttonpress()
                #pyplot.show()
                # 
                # save the image to disk / output the image to disk
                #PlotOutput = OutputDir+'/'+self.Source.Field+'--'+str(self.Source.Name)+'--'+str(self.Source.SubID)+'--'+StrTelescope+'--'+StrInstrument.replace(' ','-')+'.pdf'
                PlotDevice.savefig(PlotOutput)
                pyplot.close()
                print("")
                print("Saved as \"%s\"!"%(PlotOutput))
                # 
                # save to text file / output to text file
                #TextOutput = OutputDir+'/'+self.Source.Field+'--'+str(self.Source.Name)+'--'+str(self.Source.SubID)+'--'+StrTelescope+'--'+StrInstrument.replace(' ','-')+'.txt'
                TextFilePtr = open(TextOutput, 'w')
                TextFilePtr.write("# %s\n"%(str(datetime.now())))
                TextFilePtr.write("Source.Name = %s\n"%(self.Source.Name))
                #TextFilePtr.write("Source.ID = %ld\n"%(self.Source.ID))
                TextFilePtr.write("Source.SubID = %ld\n"%(self.Source.SubID))
                TextFilePtr.write("Source.ALMA.S/N = %.3f\n"%(self.Source.Photometry['ALMA Band 6 240 GHz S/N']))
                TextFilePtr.write("RefSource.ID = %ld\n"%(self.RefSource.ID))
                TextFilePtr.write("Match.Score = %.1f\n"%(self.Match['Score']))
                TextFilePtr.write("Match.Morphology.Score = %.1f\n"%(self.Match['Morphology']['Score']))
                TextFilePtr.write("Match.Morphology.Extended = %.1f\n"%(self.Match['Morphology']['Extended']))
                TextFilePtr.write("Match.Morphology.Polyfit = %s\n"%(self.Match['Morphology']['Polyfit']))
                TextFilePtr.write("Match.Photometry.Score = %s\n"%(str(self.Match['Photometry']['Score'])))
                TextFilePtr.write("Match.Photometry.S/N = %.3f\n"%(self.Match['Photometry']['S/N']))
                TextFilePtr.write("Match.Photometry.Flux = %.6g\n"%(self.Match['Photometry']['Flux']))
                TextFilePtr.write("Match.Photometry.FluxError = %.6g\n"%(self.Match['Photometry']['FluxError']))
                TextFilePtr.write("Match.Photometry.GrowthCurve = %s\n"%(str(self.Match['Photometry']['GrowthCurve'])))
                TextFilePtr.close()
                print("Saved to \"%s\"!"%(TextOutput))
                print("")
            # 
            # end Logger
            temp_Logger.close()


















####################################################################
#                                                                  #
#                                                                  #
#                           MAIN PROGRAM                           #
#                                                                  #
#                                                                  #
####################################################################

#Source = Highz_Galaxy(Field='COSMOS', ID=500030, SubID=1, Names={'Paper1':'Name1','Paper2':'Name2'})
#Source.about()

if len(sys.argv) <= 1:
    print("Usage: caap_highz_galaxy_crossmatcher_v5.py \"Match_cycle2_new_detections_1.5arcsec.fits\"")
    sys.exit()

# 
# Read first argument -- topcat cross-matched catalog
Input_Cat = sys.argv[1]
if not os.path.isfile(Input_Cat):
    print("Error! The input fits catalog file \"%s\" was not found!"%(Input_Cat))
    sys.exit()

Cat = Highz_Catalogue(Input_Cat)
#print(Cat.TableHeaders)

# 
# Read second argument -- cutout directory or cutout lookmap file
# <Added><20170320> -- the cutout lookmap file should contain two or three columns
#                      if two columns, should be OBJECT and cutouts file basename
#                      if three columns, should be OBJECT, DATE-OBS and cutouts file basename
Cutouts_Lookmap = {} #<Added><20170320># 
if len(sys.argv) > 2:
    Input_Cut = sys.argv[2]
    if not os.path.isfile(Input_Cut):
        if not os.path.isdir(Input_Cut):
            print("Warning! The input cutouts directory \"%s\" was not found!"%(Input_Cut))
    else:
        print("Using the input cutouts lookmap file \"%s\""%(Input_Cut))
        with open(Input_Cut,'r') as fp:
            for lp in fp:
                tmp_str_list = lp.strip().split()
                #print(len(tmp_str_list))
                if len(tmp_str_list)==2:
                    Cutouts_Lookmap[tmp_str_list[0]] = tmp_str_list[1] # use obj name
                elif len(tmp_str_list)==3:
                    Cutouts_Lookmap[tmp_str_list[1]] = tmp_str_list[2] # 
                elif len(tmp_str_list)==6:
                    Cutouts_Lookmap[(tmp_str_list[1],tmp_str_list[2],tmp_str_list[3],tmp_str_list[4])] = tmp_str_list[5] # 
            fp.close()
            #print(Cutouts_Lookmap.keys())
else:
    Input_Cut = '/home/dzliu/Temp/cutouts'

# 
# Read 3rd and hereafter arguments -- selected sources
Input_Overwrite = False
Input_DoSources = []
Input_DoSubIDs = []
Input_DoIndexes = []
for i in range(3,len(sys.argv)):
    if sys.argv[i].lower() == 'overwrite':
        # if this argument is 'overwrite'
        Input_Overwrite = True
    elif sys.argv[i].lower().startswith('index'):
        # if this argument is index number range
        Input_DoIndexes = numpy.array(sys.argv[i].lower().replace('index','').strip().split(','))
    else:
        # if this argument is source name (and subid, if separated with --)
        if sys.argv[i].find('--') > 0:
            Input_DoSources.append(sys.argv[i].split('--')[0])
            Input_DoSubIDs.append(sys.argv[i].split('--')[1])
        else:
            Input_DoSources.append(sys.argv[i])
            Input_DoSubIDs.append('*')



# 
# Loop each source in the topcat cross-matched catalog
for i in range(len(Cat.TableData)):
    
    # Check ID
    #if Cat.TableData[i].field('OBJECT') != '126982':
    #    continue
    #if Cat.TableData[i].field('OBJECT') != '141927':
    #    continue
    #if int(Cat.TableData[i].field('SUBID_TILE')) < 14:
    #    continue
    #if long(Cat.TableData[i].field('OBJECT')) < 187431:
    #    continue
    #if Cat.TableData[i].field('OBJECT') != '148443':
    #    continue
    #if Cat.TableData[i].field('OBJECT') != '238643':
    #    continue
    
    # 
    # Skip some sources that do not meet the 3rd argument, which is like "index 3~50"
    # 
    if len(Input_DoIndexes) > 0:
        Input_DoIndex_OK = False
        for Input_DoIndex in Input_DoIndexes:
            if Input_DoIndex.find('-') > 0:
                temp_str_split = Input_DoIndex.split('-')
                if len(temp_str_split) == 2:
                    if i >= long(temp_str_split[0]) and i <= long(temp_str_split[1]):
                        Input_DoIndex_OK = True
            elif Input_DoIndex.find('~') > 0:
                temp_str_split = Input_DoIndex.split('~')
                if len(temp_str_split) == 2:
                    if i >= long(temp_str_split[0]) and i <= long(temp_str_split[1]):
                        Input_DoIndex_OK = True
            elif Input_DoIndex.find(' ') > 0:
                temp_str_split = Input_DoIndex.split(' ')
                for temp_str_item in temp_str_split:
                    if i == long(temp_str_item):
                        Input_DoIndex_OK = True
            else:
                if i == long(Input_DoIndex):
                    Input_DoIndex_OK = True
        # 
        if not Input_DoIndex_OK:
            continue
    
    # 
    # Skip some sources that do not meet the 3rd argument, which is like "SOURCE-NAME--SUBID"
    # 
    if len(Input_DoSources) > 0:
        if Cat.TableData[i].field('OBJECT') not in Input_DoSources:
            Input_DoSubID = '*'
            continue
        else:
            Input_DoSubID = [DoSubID for DoSource, DoSubID in zip(Input_DoSources,Input_DoSubIDs) if DoSource == Cat.TableData[i].field('OBJECT')]
            Input_DoSubID = Input_DoSubID[0]
        # 
        if Input_DoSubID != '*':
            if Cat.TableData[i].field('SUBID_TILE') != long(Input_DoSubID):
                continue
    
    
    
    Overwrite = Input_Overwrite
    
    # 
    # Check Source Morphology
    # 
    source_maj = numpy.nan
    source_min = numpy.nan
    source_pa = numpy.nan
    if 'FWHM_MAJ_FIT' in Cat.TableHeaders and \
       'FWHM_MIN_FIT' in Cat.TableHeaders and \
       'POSANG_FIT' in Cat.TableHeaders and \
       'MINAX_BEAM' in Cat.TableHeaders and \
       'AXRATIO_BEAM' in Cat.TableHeaders and \
       'POSANG_BEAM' in Cat.TableHeaders:
        source_maj = float(Cat.TableData[i].field('FWHM_MAJ_FIT'))
        source_min = float(Cat.TableData[i].field('FWHM_MIN_FIT'))
        source_pa = float(Cat.TableData[i].field('POSANG_FIT'))
        beam_maj = float(Cat.TableData[i].field('MINAX_BEAM')) * float(Cat.TableData[i].field('AXRATIO_BEAM'))
        beam_min = float(Cat.TableData[i].field('MINAX_BEAM'))
        beam_pa = float(Cat.TableData[i].field('POSANG_BEAM'))
        # prevent source size too small
        if source_maj*source_min < beam_maj*beam_min:
            source_maj = beam_maj
            source_min = beam_min
            source_pa = beam_pa
    if source_maj != source_maj or source_min != source_min or source_pa != source_pa:
        print("")
        print("Error! Could not find appropriate columns in the input topcat cross-matched catalog!")
        print("We need 'FWHM_MAJ_FIT', 'FWHM_MIN_FIT', 'POSANG_FIT', 'MINAX_BEAM', 'AXRATIO_BEAM', 'POSANG_BEAM', etc.")
        print("Abort!")
        print("")
        sys.exit()
    
    # 
    # Read info
    # 
    if 'OBJECT' in Cat.TableHeaders:
        source_Name = Cat.TableData[i].field('OBJECT').strip()
    if 'PROJECT' in Cat.TableHeaders:
        source_Name = Cat.TableData[i].field('PROJECT').strip()+'--'+source_Name
    if 'SUBID_TILE' in Cat.TableHeaders:
        source_SubID = Cat.TableData[i].field('SUBID_TILE')
    if 'RA' in Cat.TableHeaders:
        source_RA = Cat.TableData[i].field('RA')
    if 'RA_1' in Cat.TableHeaders:
        source_RA = Cat.TableData[i].field('RA_1')
    if 'DEC' in Cat.TableHeaders:
        source_DEC = Cat.TableData[i].field('DEC')
    if 'DEC_1' in Cat.TableHeaders:
        source_DEC = Cat.TableData[i].field('DEC_1')
    if 'ZPDF' in Cat.TableHeaders:
        source_z = { 'Laigle 2015 photo-z': float(Cat.TableData[i].field('ZPDF')) }
    else:
        source_z = { 'Laigle 2015 photo-z': -99.0 }
    
    #if 'OBS_DATE' in Cat.TableHeaders:
    #    source_Date = Cat.TableData[i].field('OBS_DATE').strip()
    #    # I tried to use DATE-OBS to distinguish fields in a same obs scan but failed. 
    #    # Now I have to check the RA Dec to determine cutouts lookmap.
    
    # 
    # Create ALMA Source
    # 
    # <TODO>    ID      = re.sub('[!@#$a-zA-Z_]', '', Cat.TableData[i].field('OBJECT')), 
    Source = Highz_Galaxy(
        Field   = 'COSMOS', 
        Name    = source_Name, 
        SubID   = source_SubID, 
        RA      = source_RA, 
        Dec     = source_DEC, 
        Morphology = {
            'Major Axis': source_maj, 
            'Minor Axis': source_min, 
            'Pos Angle':  source_pa, 
        }, 
        Photometry = {
            'ALMA Band 6 240 GHz S/N': float(Cat.TableData[i].field('SNR_FIT'))
        }, 
        Redshifts = source_z, 
    )
    Source.about()
    
    # 
    # Create Counterpart Source from Laigle 2015 Catalog
    # 
    if 'NUMBER' in Cat.TableHeaders:
        refsource_ID = Cat.TableData[i].field('NUMBER')
        refsource_Names = { 'Laigle 2015': str(Cat.TableData[i].field('NUMBER')) }
    if 'ID' in Cat.TableHeaders:
        refsource_ID = Cat.TableData[i].field('ID')
        refsource_Names = { 'Sanders IRAC Catalog': str(Cat.TableData[i].field('ID')) }
    if 'ALPHA_J2000' in Cat.TableHeaders:
        refsource_RA = Cat.TableData[i].field('ALPHA_J2000')
    if 'RA_2' in Cat.TableHeaders:
        refsource_RA = Cat.TableData[i].field('RA_2')
    if 'DELTA_J2000' in Cat.TableHeaders:
        refsource_DEC = Cat.TableData[i].field('DELTA_J2000')
    if 'DEC_2' in Cat.TableHeaders:
        refsource_DEC = Cat.TableData[i].field('DEC_2')
    RefSource = Highz_Galaxy(
        Field = 'COSMOS', 
        Name  = refsource_ID, 
        ID    = refsource_ID, 
        RA    = refsource_RA, 
        Dec   = refsource_DEC, 
        Names = refsource_Names
    )
    
    # 
    # Prepare cutouts and copy to CutoutOutputDir
    # 
    CutoutOutputDir = 'cutouts'
    CutoutOutputName = 'cutouts_temporary' # 'cutouts_'+Source.Name #<20170320><TODO># Source.Name not unique
    CutoutFileFindingStr = 'N/A'
    CutoutFilePaths = []
    if not os.path.isdir(CutoutOutputDir):
        os.mkdir(CutoutOutputDir)
    # 
    # check if we have already cutouts for each source (from previous runs)
    # 
    if not os.path.isdir("%s/%s"%(CutoutOutputDir, CutoutOutputName)):
        os.mkdir("%s/%s"%(CutoutOutputDir, CutoutOutputName))
    #<20170320><TODO>#else:
    #<20170320><TODO>#    CutoutFileFindingStr = "%s/%s/*.fits"%(CutoutOutputDir, CutoutOutputName) # cutout fits file names always contain ID but not full names. 
    # 
    # Copy cutouts from Input_Cut directory
    # 
    # -- use Cutouts_Lookmap
    #    and Cutouts_Lookmap is using Object Name to look for cutouts image file
    if CutoutFileFindingStr == 'N/A':
        if source_Name in Cutouts_Lookmap.keys():
            print("Found cutouts in cutouts lookmap file for object name \"%s\""%(source_Name))
            CutoutFileFindingStr = "%s"%(Cutouts_Lookmap[source_Name])
    # -- use Cutouts_Lookmap
    #    and Cutouts_Lookmap is using Object RA Dec to look for cutouts image file
    if CutoutFileFindingStr == 'N/A':
        Cutouts_Lookmap_Polygon_Center_Selected = []
        for Cutouts_Lookmap_Key in Cutouts_Lookmap.keys():
            if type(Cutouts_Lookmap_Key) is tuple:
                if len(Cutouts_Lookmap_Key) == 4:
                    Cutouts_Lookmap_Rectangle = numpy.array(Cutouts_Lookmap_Key).astype(numpy.float)
                    #print(Cutouts_Lookmap_Rectangle, len(Cutouts_Lookmap_Rectangle))
                    Cutouts_Lookmap_Polygon_Center = (
                        (Cutouts_Lookmap_Rectangle[0]+Cutouts_Lookmap_Rectangle[1])/2.0, \
                        (Cutouts_Lookmap_Rectangle[2]+Cutouts_Lookmap_Rectangle[3])/2.0
                        )
                    Cutouts_Lookmap_Polygon = matplotlib.path.Path([ \
                        [Cutouts_Lookmap_Rectangle[0],Cutouts_Lookmap_Rectangle[2]], \
                        [Cutouts_Lookmap_Rectangle[0],Cutouts_Lookmap_Rectangle[3]], \
                        [Cutouts_Lookmap_Rectangle[1],Cutouts_Lookmap_Rectangle[3]], \
                        [Cutouts_Lookmap_Rectangle[1],Cutouts_Lookmap_Rectangle[2]], \
                        [Cutouts_Lookmap_Rectangle[0],Cutouts_Lookmap_Rectangle[2]] \
                        ])
                    #print(Cutouts_Lookmap_Polygon)
                    if Cutouts_Lookmap_Polygon.contains_point((source_RA,source_DEC)):
                        print("Found cutouts in cutouts lookmap file for object RA Dec %.7f %.7f"%(source_RA, source_DEC))
                        if len(Cutouts_Lookmap_Polygon_Center_Selected) == 0:
                            Cutouts_Lookmap_Polygon_Center_Selected = Cutouts_Lookmap_Polygon_Center
                            CutoutFileFindingStr = "%s"%(Cutouts_Lookmap[Cutouts_Lookmap_Key])
                        else:
                            if ((source_RA-Cutouts_Lookmap_Polygon_Center[0])**2 + (source_DEC-Cutouts_Lookmap_Polygon_Center[1])**2) < ((source_RA-Cutouts_Lookmap_Polygon_Center_Selected[0])**2 + (source_DEC-Cutouts_Lookmap_Polygon_Center_Selected[1])**2):
                                Cutouts_Lookmap_Polygon_Center_Selected = Cutouts_Lookmap_Polygon_Center
                                CutoutFileFindingStr = "%s"%(Cutouts_Lookmap[Cutouts_Lookmap_Key])
    if CutoutFileFindingStr == 'N/A':
        CutoutFileFindingStr = "%s/*/%s[._]*.fits"%(Input_Cut, Source.Name)
    # 
    # Search for cutouts image files
    # 
    print("Searching cutouts image files with pattern \"%s\""%(CutoutFileFindingStr))
    CutoutFilePaths = glob.glob(CutoutFileFindingStr)
    
    
    # 
    # List cutouts (Source.Name[._]*.fits)
    # 
    CutoutFileNames = []
    if len(CutoutFilePaths)==0:
        print("**********************************************************************************************************************")
        print("Error! Could not find fits image cutouts: \"%s\"! Will skip current source \"%s\"!"%(CutoutFileFindingStr, Source.Name))
        print("**********************************************************************************************************************")
        #sys.exit()
        continue
    else:
        # Copy Cutouts fits files and store file names
        for CutoutFilePath in CutoutFilePaths:
            CutoutFileName = os.path.basename(CutoutFilePath)
            if  ( (CutoutFileName.find('_acs_I_mosaic_')>=0) or \
                  (CutoutFileName.find('_irac_ch')>=0) or \
                  (CutoutFileName.find('_mips_24_GO3_')>=0) or \
                  (CutoutFileName.find('.J.original-psf.')>=0) or \
                  (CutoutFileName.find('.H.original_psf.')>=0) or \
                  (CutoutFileName.find('.Ks.original_psf.')>=0) 
                ) :
                # 
                # (CutoutFileName.find('_vla_20cm_dp')>=0)
                # (CutoutFileName.find('_vla_3ghz')>=0)
                # 
                CutoutFileNames.append("%s/%s/%s"%(CutoutOutputDir, CutoutOutputName, CutoutFileName))
                # 
                if not os.path.isfile("%s/%s/%s"%(CutoutOutputDir, CutoutOutputName, CutoutFileName)):
                    print("Copying cutouts image file \"%s\" to \"%s/%s/%s\""%(CutoutFilePath, CutoutOutputDir, CutoutOutputName, CutoutFileName))
                    shutil.copy2(CutoutFilePath, "%s/%s/%s"%(CutoutOutputDir, CutoutOutputName, CutoutFileName))
        # 
        pprint(CutoutFilePaths)
        pprint(CutoutFileNames)
        #sys.exit()
    
    
    
    # 
    # 
    # Do CrossMatching on each cutout image (i.e. each band)
    # 
    # 
    for CutoutFileName in CutoutFileNames:
        # 
        # CrossMatch_Identifier can only process one fits image at a same time
        # match_morphology() is the core function to do cross-matching
        IDX = CrossMatch_Identifier(
            Source = Source, 
            RefSource = RefSource, 
            FitsImageFile = CutoutFileName
        )
        IDX.about()
        IDX.match_morphology(Overwrite=Overwrite, OutputName=str(i))
        #break
    
    #break












