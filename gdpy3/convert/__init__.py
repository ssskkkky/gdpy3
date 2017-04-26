# -*- coding: utf-8 -*-

# Copyright (c) 2017 shmilee

r'''
    This is the subpackage ``convert`` of package gdpy3.
'''

__all__ = ['convert', 'data1d', 'gtcout', 'history', 'snapshot']

import os
import sys
import time
import logging
from . import data1d, gtcout, history, snapshot

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    # format='[%(asctime)s %(name)s] %(levelname)s - %(message)s',
    # datefmt='%Y-%m-%d %H:%M:%S',
    format='[%(name)s]%(levelname)s - %(message)s'
)

log = logging.getLogger('gdc')

__FileClassMapDict = {
    '110922': {
        'gtc.out': gtcout.GtcOutV110922,
        'data1d.out': data1d.Data1dBlockV110922,
        'history.out': history.HistoryBlockV110922,
        'snapshot.out': snapshot.SnapshotBlockV110922,
    }
}


def convert(datadir, savepath, **kwargs):
    '''Read all GTC .out files in directory ``datadir``.
    Save the results in ``savepath``.

    Parameters
    ----------
    datadir: str
        the path of GTC .out files
    savepath: str
        path of file which the data is save
    kwargs: other parameters
        ``loglevel`` for setting log level
        ``description`` description of the simulation case
        ``version`` for setting gtc version, default is 110922
        ``additionalpats`` for reading gtc.out

    Notes
    -----
    1) GTC .out files should be named as:
       gtc.out, data1d.out, history.out, snap("%05d" % istep).out, etc.
       so that they can be auto-detected.
    2) ``additionalpats`` should be a list. See gtcout.convert.
    3) The ``savepath`` extension defines the filetype of saved data,
       which may be ``npz``, ``hdf5`` or ``mat``.
       If no one is matched, ".npz" will be adopted.

    Raises
    ------
    IOError
        Can't read .out files in``datadir``, or save file in ``savepath``.
    '''

    if not datadir:
        raise IOError("Please set the path of GTC .out files!")
    if not os.path.isdir(datadir):
        raise IOError("Can't find directory '%s'!" % datadir)
    if not os.access(os.path.dirname(savepath), os.W_OK):
        raise IOError("Can't access directory '%s'!" %
                      os.path.dirname(savepath))
    if not os.path.isfile(datadir + '/gtc.out'):
        raise IOError("Can't find 'gtc.out' in '%s'!" % datadir)

    if 'loglevel' in kwargs:
        loglevel = getattr(logging, kwargs['loglevel'].upper(), None)
        if isinstance(loglevel, int):
            log.setLevel(loglevel)

    if 'version' in kwargs and str(kwargs['version']) in __FileClassMapDict:
        __version = str(kwargs['version'])
    else:
        __version = '110922'
    log.info("Set the GTC data version: '%s'." % __version)
    FlClsMp = __FileClassMapDict[__version]

    # get gtc.out parameters
    paras = FlClsMp['gtc.out'](file=datadir + '/gtc.out')
    if 'additionalpats' in kwargs and type(kwargs['additionalpats']) is list:
        paras.convert(additionalpats=kwargs['additionalpats'])
    else:
        log.info('getting data from %s ...' % paras.file)
        paras.convert()

    # description for this case
    desc = ("GTC .out data from directory '%s'.\n"
            "Created by gdpy3.convert: '%s'.\n"
            "Created on: %s." %
            (datadir, __version, time.asctime()))
    if 'description' in kwargs:
        desc = desc + '\n' + str(kwargs['description'])

    # prepare savepath
    saveext = os.path.splitext(savepath)[1]
    # default filetype is '.npz'
    if saveext not in ('.npz', '.hdf5', '.mat'):
        log.warn("Filetype of savepath should be '.npz', '.hdf5' or '.mat'!")
        log.info("Use '.npz'.")
        saveext = '.npz'
        savepath = savepath + '.npz'
    # TODO(nobody): delete this, when '.mat' is ready.
    if saveext == '.mat':
        log.warn("'.mat' is not ready. Use '.npz'.")
        saveext = '.npz'
        savepath = savepath + '.npz'

    # save all data
    def _get_fcls(f):
        if f in ('data1d.out', 'history.out'):
            return FlClsMp[f](file=datadir + '/' + f)
        elif 'the-snap' in 'the-' + f:
            return FlClsMp['snapshot.out'](file=datadir + '/' + f)
        else:
            return None

    if saveext == '.npz':
        try:
            from . import wrapnpz as wrapfile
        except ImportError:
            log.error("Failed to import 'wrapnpz'!")
            raise
    elif saveext == '.hdf5':
        try:
            from . import wraphdf5 as wrapfile
        except ImportError:
            log.error("Failed to import 'wraphdf5'!")
            raise
    elif saveext == '.mat':
        try:
            from . import wrapmat as wrapfile
        except ImportError:
            log.error("Failed to import 'wrapmat'!")
            raise

    if os.path.isfile(savepath):
        log.warn("Remove file: '%s'!" % savepath)
        os.remove(savepath)

    savefid = wrapfile.iopen(savepath)
    wrapfile.write(savefid, '/', {'description': desc})
    wrapfile.write(savefid, paras.name, paras.data)
    for f in sorted(os.listdir(datadir)):
        fcls = _get_fcls(f)
        if not fcls:
            continue
        try:
            log.info('getting data from %s ...' % fcls.file)
            fcls.convert()
            wrapfile.write(savefid, fcls.name, fcls.data)
        except:
            log.error('Failed to get data from %s.' % fcls.file)
    wrapfile.close(savefid)

    log.info("GTC '.out' files in %s are converted to %s!" %
             (datadir, savepath))
