# -*- coding: utf-8 -*-

# Copyright (c) 2019 shmilee

'''
Contains processor base class.
'''

import os
import re
import time
import pickle
import hashlib

from .. import __version__ as gdpy3_version
from ..glogger import getGLogger
from ..loaders import is_rawloader, get_rawloader, is_pckloader, get_pckloader
from ..savers import is_pcksaver, get_pcksaver
from ..cores.exporter import (TmplLoader, ContourfExporter, LineExporter,
                              SharexTwinxExporter, Z111pExporter)
from ..visplters import get_visplter, is_visplter

__all__ = ['Processor']
plog = getGLogger('P')


class Processor(object):
    '''
    Serial Processor class.

    Attributes
    ----------

    name: class name of this processor
    rawloader: rawloader object to get raw data
    converters: converter cores to convert raw data to pickled data
    pcksaver: pcksaver object to save pickled data

    pckloader: pckloader object to get pickled data
    ressaver: cachepcksaver object to save dig results
    resfilesaver: pcksaver object to save long time dig results
    diggers: digger cores to calculate pickled data to results
    availablelabels: list
        figure labels in this processor, like 'group/fignum'
    resloader: cachepckloader object to get dig results
    resfileloader: pckloader object to get long time dig results
    diggedlabels: set
        figlabels/kwargstr digged in ressaver or resfilesaver
        like 'group/fignum/a=1,b=2'

    tmplloader: loader of exporter templates
    exportertemplates: list
        exporter templates supported

    Notes
    -----
    1. :attr:`saltname` means base name of salt file for `saver.path`.
       The :attr:`rawloader` must have exactly one salt file.
    2. :attr:`dig_acceptable_time` means if :meth:`dig` spends more
       time than this, the results will be saved in :attr:`resfilesaver`.
    '''

    @property
    def name(self):
        return type(self).__name__

    # # Start Convert Part

    __slots__ = ['_rawloader', '_pcksaver', '_converters']
    ConverterCores = []
    saltname = ''

    def __check_rawloader(self, rawloader):
        if not is_rawloader(rawloader):
            plog.error("%s: Not a rawloader object!" % self.name)
            return False
        saltfiles = rawloader.refind('^(?:|.*/)%s$' % self.saltname)
        if len(saltfiles) == 0:
            plog.error("%s: Can't find '%s' in '%s'!"
                       % (self.name, self.saltname, rawloader.path))
            return False
        elif len(saltfiles) > 1:
            plog.error("%s: More than one '%s' found in '%s'!"
                       % (self.name, self.saltname, rawloader.path))
            return False
        else:
            return saltfiles[0]

    def _get_rawloader(self):
        return self._rawloader

    def _set_rawloader(self, rawloader):
        self._converters = []
        if rawloader and self.__check_rawloader(rawloader):
            self._rawloader = rawloader
            for Cc in self.ConverterCores:
                self._converters.extend(Cc.generate_cores(rawloader))
        else:
            self._rawloader = None
    rawloader = property(_get_rawloader, _set_rawloader)

    @property
    def converters(self):
        return self._converters

    def _get_pcksaver(self):
        return self._pcksaver

    def _set_pcksaver(self, pcksaver):
        if is_pcksaver(pcksaver):
            self._pcksaver = pcksaver
        else:
            self._pcksaver = None

    pcksaver = property(_get_pcksaver, _set_pcksaver)

    def set_prefer_pcksaver(self, savetype, ext2='converted'):
        '''
        Set preferable pcksaver path beside raw data.

        Parameters
        ----------
        savetype: str
            extension of pcksaver.path, like (.npz)
        ext2: str
            second extension, like name.(converted).npz
        '''
        if not self.rawloader:
            raise IOError("%s: Need a rawloader object!" % self.name)
        # salt
        saltfile = self.rawloader.refind('^(?:|.*/)%s$' % self.saltname)[0]
        if self.rawloader.loader_type in ['sftp.directory']:
            salt = hashlib.sha1(saltfile.encode('utf-8')).hexdigest()
        else:
            try:
                with self.rawloader.get(saltfile) as f:
                    salt = hashlib.sha1(f.read().encode('utf-8')).hexdigest()
            except Exception:
                plog.warning("Failed to read salt file '%s'!" % saltfile)
                salt = hashlib.sha1(saltfile.encode('utf-8')).hexdigest()
        plog.debug("Get salt string: '%s'." % salt)
        # prefix
        prefix = self.rawloader.beside_path(self.name.lower())
        # savetype
        if os.access(os.path.dirname(prefix), os.W_OK):
            if savetype not in ['.npz', '.hdf5']:
                plog.warning("Use default savetype '.npz'.")
                savetype = '.npz'
        else:
            plog.debug("Use savetype '.cache' because %s isn't writable!"
                       % os.path.dirname(prefix))
            savetype = '.cache'
        # assemble
        savepath = '%s-%s.%s%s' % (prefix, salt[:6], ext2, savetype)
        self.pcksaver = get_pcksaver(savepath)

    @property
    def _rawsummary(self):
        return "Raw data files in %s '%s'" % (
            self.rawloader.loader_type, self.rawloader.path)

    def convert(self, add_desc=None):
        '''
        Convert raw data in rawloader.path, and save them in pcksaver.
        '''
        if not self.rawloader:
            plog.error("%s: Need a rawloader object!" % self.name)
            return
        if not self.pcksaver:
            plog.error("%s: Need a pcksaver object!" % self.name)
            return
        summary = "Pck data converted from %s." % self._rawsummary
        description = ("%s\nCreated by gdpy3 v%s.\nCreated on %s."
                       % (summary, gdpy3_version, time.asctime()))
        if add_desc:
            description += '\n' + str(add_desc)
        with self.pcksaver:
            self.pcksaver.write('/', {'description': description,
                                      'processor': self.name})
            for core in self.converters:
                self.pcksaver.write(core.group, core.convert())
        plog.info("%s are converted to %s!"
                  % (self._rawsummary,  self.pcksaver.path))

    # # End Convert Part

    # # Start Dig Part

    __slots__.extend(['_pckloader', '_ressaver', '_resfilesaver',
                      '_diggers', '_availablelabels_lib', '_availablelabels',
                      '_resloader', '_resfileloader', '_diggedlabels'])
    DiggerCores = []
    dig_acceptable_time = 30

    def __check_pckloader(self, pckloader):
        if not is_pckloader(pckloader):
            plog.error("%s: Not a pckloader object!" % self.name)
            return
        if 'processor' not in pckloader:
            plog.error("%s: Can't find 'processor' in '%s'!"
                       % (self.name, pckloader.path))
            return False
        pname = pckloader.get('processor')
        if pname != self.name:
            plog.error("%s: Invalid 'processor' '%s'! Did you mean '%s'?"
                       % (self.name, pname, self.name))
            return False
        return True

    def _get_pckloader(self):
        return self._pckloader

    def _set_pckloader(self, pckloader):
        self._diggers = []
        if pckloader and self.__check_pckloader(pckloader):
            self._pckloader = pckloader
            for Dc in self.DiggerCores:
                self._diggers.extend(Dc.generate_cores(pckloader))
        else:
            self._pckloader = None
        self._availablelabels_lib = {dc.figlabel: dc for dc in self._diggers}
        self._availablelabels = sorted(self._availablelabels_lib.keys())

    pckloader = property(_get_pckloader, _set_pckloader)

    @property
    def diggers(self):
        return self._diggers

    @property
    def availablelabels(self):
        return self._availablelabels

    # save results
    def _get_ressaver(self):
        return self._ressaver

    def _set_ressaver(self, ressaver):
        if is_pcksaver(ressaver):
            self._ressaver = ressaver
        else:
            self._ressaver = None

    ressaver = property(_get_ressaver, _set_ressaver)

    def _get_resfilesaver(self):
        return self._resfilesaver

    def _set_resfilesaver(self, resfilesaver):
        if is_pcksaver(resfilesaver):
            self._resfilesaver = resfilesaver
        else:
            self._resfilesaver = None

    resfilesaver = property(_get_resfilesaver, _set_resfilesaver)

    # reload results
    def _get_resloader(self):
        return self._resloader

    def _set_resloader(self, resloader):
        if not getattr(self, '_diggedlabels', None):
            self._diggedlabels = set()
        if resloader and self.__check_pckloader(resloader):
            self._resloader = resloader
            self._diggedlabels.update(resloader.datagroups)
        else:
            self._resloader = None

    resloader = property(_get_resloader, _set_resloader)

    def _get_resfileloader(self):
        return self._resfileloader

    def _set_resfileloader(self, resfileloader):
        if not getattr(self, '_diggedlabels', None):
            self._diggedlabels = set()
        if resfileloader and self.__check_pckloader(resfileloader):
            self._resfileloader = resfileloader
            self._diggedlabels.update(resfileloader.datagroups)
        else:
            self._resfileloader = None

    resfileloader = property(_get_resfileloader, _set_resfileloader)

    @property
    def diggedlabels(self):
        return self._diggedlabels

    def set_prefer_ressaver(self, ext2='digged', overwrite=False):
        '''
        Set preferable ressaver resfilesaver beside converted data.

        Parameters
        ----------
        ext2: str
            second extension, like name.(digged).npz
        overwrite: bool
            overwrite existing resfilesaver.path file or not, default False
        '''
        if not self.pckloader:
            raise IOError("%s: Need a pckloader object!" % self.name)
        saverstr, ext = os.path.splitext(self.pckloader.path)
        saverstr = saverstr.replace('converted', ext2)
        respath = '%s.cache' % saverstr
        ressaver = get_pcksaver(respath)
        with ressaver:
            ressaver.write('/', {'processor': self.name})
        self.ressaver = ressaver
        self.resloader = get_pckloader(ressaver.get_store())
        plog.debug("Default %s data cache is %s." % (ext2, respath))
        if ext != '.cache':
            try:
                respath = '%s%s' % (saverstr, ext)
                resfilesaver = get_pcksaver(respath)
                if overwrite and os.path.isfile(respath):
                    plog.warning("Remove old %s data file: %s!"
                                 % (ext2, respath))
                    os.remove(respath)
                if not os.path.isfile(respath):
                    # new file
                    with resfilesaver:
                        resfilesaver.write('/', {'processor': self.name})
                self.resfilesaver = resfilesaver
                self.resfileloader = get_pckloader(resfilesaver.get_store())
                plog.info("Default %s data path is %s." % (ext2, respath))
            except Exception:
                plog.error("%s: Failed to set results file pcksaver, '%s'!"
                           % (self.name, respath), exc_info=1)
                self.resfilesaver = None

    def dig(self, figlabel, post=True, redig=False, **kwargs):
        '''
        Get digged results of *figlabel*.
        Use :meth:`dig_doc` to see *kwargs* for *figlabel*.
        Return accfiglabel, results and template name,
        and accfiglabel is 'figlabel/digkwargstr'.

        Parameters
        ----------
        post: bool
        redig: bool
            If :attr:`resfilesaver` type is '.npz', *redig* will cause warning:
                "zipfile.py: UserWarning: Duplicate name ..."
            Recommend using '.hdf5' when *redig* is True.
        '''
        if not self.pckloader:
            plog.error("%s: Need a pckloader object!" % self.name)
            return None, None, None
        if not self.ressaver:
            plog.error("%s: Need a results pcksaver object!" % self.name)
            return None, None, None
        if figlabel not in self.availablelabels:
            plog.error("%s: Figure %s not found!" % (self.name, figlabel))
            return None, None, None
        digcore = self._availablelabels_lib[figlabel]
        gotkwargstr = digcore.str_dig_kwargs(kwargs) or 'DEFAULT'
        gotfiglabel = '%s/%s' % (figlabel, gotkwargstr)
        # find old
        if not redig and gotfiglabel in self.diggedlabels:
            if gotfiglabel in self.resloader.datagroups:
                # use resloader first
                gotresloader, fileloader = self.resloader, False
            elif (self.resfilesaver
                    and gotfiglabel in self.resfileloader.datagroups):
                gotresloader, fileloader = self.resfileloader, True
            else:
                gotresloader, fileloader = None, False
                plog.error('%s: Not found %s in diggedlabels!'
                           % (self.name, gotfiglabel))
            if gotresloader:
                plog.info('Find %s digged results in %s.'
                          % (gotfiglabel, gotresloader.path))
                allkeys = gotresloader.refind(
                    '^%s/' % re.escape(gotfiglabel))
                basekeys = [os.path.basename(k) for k in allkeys]
                resultstuple = gotresloader.get_many(*allkeys)
                results = {k: v for k, v in zip(basekeys, resultstuple)}
                if fileloader:
                    # reload kwoptions
                    digcore.kwoptions = pickle.loads(
                        results.pop('kwoptions', None))
                if post:
                    results = digcore.post_dig(results)
                return gotfiglabel, results, digcore.post_template
        # dig new
        results, acckwargstr, digtime = digcore.dig(**kwargs)
        if not acckwargstr:
            acckwargstr = 'DEFAULT'
        accfiglabel = '%s/%s' % (figlabel, acckwargstr)
        with self.ressaver:
            self.ressaver.write(accfiglabel, results)
            if gotkwargstr == 'DEFAULT' and acckwargstr != gotkwargstr:
                # TODO link double cache
                self.ressaver.write(gotfiglabel, results)
        # update resloader & diggedlabels
        self.resloader = get_pckloader(self.ressaver.get_store())
        # long execution time
        if self.resfilesaver and digtime > self.dig_acceptable_time:
            # also save kwoptions
            if digcore.kwoptions is None:
                plog.warning('Unset %s kwoptions!' % figlabel)
            kwopts = dict(kwoptions=pickle.dumps(digcore.kwoptions))
            with self.resfilesaver:
                plog.info('Save digged results in %s.' %
                          self.resfilesaver.path)
                self.resfilesaver.write(accfiglabel, results)
                self.resfilesaver.write(accfiglabel, kwopts)
                if gotkwargstr == 'DEFAULT' and acckwargstr != gotkwargstr:
                    # TODO link double cache
                    self.resfilesaver.write(gotfiglabel, results)
                    self.resfilesaver.write(gotfiglabel, kwopts)
            # update resfileloader & diggedlabels
            self.resfileloader = get_pckloader(self.resfilesaver.get_store())
        if post:
            results = digcore.post_dig(results)
        return accfiglabel, results, digcore.post_template

    def dig_doc(self, figlabel, see='help'):
        '''
        help(digcore.dig) or digcore.dig.__doc__

        Parameters
        ----------
        see: str
            'help', 'print' or 'return'
        '''
        if figlabel not in self.availablelabels:
            plog.error("%s: Figure %s not found!" % (self.name, figlabel))
            return
        digcore = self._availablelabels_lib[figlabel]
        if see == 'help':
            help(digcore.dig)
        elif see == 'print':
            print(digcore.dig.__doc__)
        elif see == 'return':
            return digcore.dig.__doc__
        else:
            pass

    def refind(self, pattern):
        '''Find the figlabels which match the regular expression *pattern*.'''
        pat = re.compile(pattern)
        return tuple(filter(
            lambda k: True if re.match(pat, k) else False, self.availablelabels))

    # # End Dig Part

    # # Start Export Part

    __slots__.extend(['_tmplloader', '_exportertemplates', '_exporters_lib'])
    ExporterCores = [ContourfExporter, LineExporter,
                     SharexTwinxExporter, Z111pExporter]

    def _get_tmplloader(self):
        return self._tmplloader

    def _set_tmplloader(self, tmplloader):
        self._exportertemplates = []
        self._exporters_lib = {}
        if tmplloader:
            self._tmplloader = tmplloader
            for Ec in self.ExporterCores:
                self._exporters_lib.update({ec.template: ec
                                            for ec in Ec.generate_cores(tmplloader)})
            self._exportertemplates = sorted(self._exporters_lib.keys())
        else:
            self._tmplloader = None

    tmplloader = property(_get_tmplloader, _set_tmplloader)

    @property
    def exportertemplates(self):
        return self._exportertemplates

    def export(self, figlabel, what='axes', fmt='dict', **kwargs):
        '''
        Get and assemble digged results, template of *figlabel*.
        Use :meth:`dig_doc` to see *kwargs* for *figlabel*.
        Use :meth:`export_doc` to see *kwargs* for :meth:`exportcore.export`.

        Returns
        -------
        assembled results in format *fmt*
        If *what* is 'axes', results['accfiglabel'] will be updated
        from 'figlabel/digkwargstr' to 'figlabel/digkwargstr,viskwargstr',
        where 'viskwargstr' is :meth:`exportcore.export` *kwargs* to str.

        Parameters
        ----------
        what: str
            'axes', results for visplter
            'options', options for GUI widgets
        fmt: str
            export format, 'dict', 'pickle' or 'json'
        '''
        if figlabel not in self.availablelabels:
            plog.error("%s: Figure %s not found!" % (self.name, figlabel))
            exportcore = self._exporters_lib[self.exportertemplates[0]]
            return exportcore.fmt_export(
                dict(status='figlabel not found',
                     figlabel=figlabel,
                     ), fmt=fmt)
        if what == 'axes':
            label_kw, res, tmpl = self.dig(figlabel, post=True, **kwargs)
            if tmpl in self.exportertemplates:
                exportcore = self._exporters_lib[tmpl]
                return exportcore.export(
                    res, otherinfo=dict(status='success',
                                        figlabel=figlabel,
                                        accfiglabel=label_kw,
                                        ), fmt=fmt, **kwargs)
            else:
                return exportcore.fmt_export(
                    dict(status='no template', figlabel=figlabel), fmt=fmt)
        elif what == 'options':
            digcore = self._availablelabels_lib[figlabel]
            if digcore.kwoptions is None:
                a, b, c = self.dig(figlabel, post=False, **kwargs)
            if digcore.post_template in self.exportertemplates:
                exportcore = self._exporters_lib[digcore.post_template]
                return exportcore.export_options(
                    digcore.kwoptions, otherinfo=dict(status='success',
                                                      figlabel=figlabel,
                                                      ), fmt=fmt)
            else:
                exportcore = self._exporters_lib[self.exportertemplates[0]]
                return exportcore.fmt_export(
                    dict(status='no visoptions',
                         figlabel=figlabel,
                         digoptions=digcore.kwoptions,
                         ), fmt=fmt)
        else:
            plog.error("%s: What to export, 'axes' or 'options'?" % self.name)
            exportcore = self._exporters_lib[self.exportertemplates[0]]
            return exportcore.fmt_export(
                dict(status='what to export',
                     figlabel=figlabel,
                     ), fmt=fmt)

    def export_doc(self, template, see='help'):
        '''
        help(exportercore.export) or exportercore.export.__doc__

        Parameters
        ----------
        see: str
            'help', 'print' or 'return'
        '''
        if template not in self.exportertemplates:
            plog.error("%s: Template %s not found!" % (self.name, template))
            return
        exportcore = self._exporters_lib[template]
        if see == 'help':
            help(exportcore.export)
        elif see == 'print':
            print(exportcore.export.__doc__)
        elif see == 'return':
            return exportcore.export.__doc__
        else:
            pass

    # # End Export Part

    # # Start Visplt Part

    __slots__.extend(['_visplter'])

    def _get_visplter(self):
        return self._visplter

    def _set_visplter(self, visplter):
        if is_visplter(visplter):
            self._visplter = visplter
        else:
            self._visplter = visplter

    visplter = property(_get_visplter, _set_visplter)

    def visplt(self, figlabel, revis=False, show=True, **kwargs):
        '''
        Get results of *figlabel* and visualize(plot).
        Use :meth:`dig_doc` :meth:`export_doc` to see *kwargs* for *figlabel*.
        Return accfiglabel or None.

        Parameters
        ----------
        revis: bool
            replot *figlabel* if it was already ploted
        show: bool
            display *figlabel* after it ploted
        '''
        if not self.visplter:
            plog.error("%s: Need a visplter object!" % self.name)
            return
        results = self.export(figlabel, what='axes', fmt='dict', **kwargs)
        if results['status'] == 'success':
            try:
                self.visplter.create_template_figure(results, replace=revis)
            except Exception:
                plog.error("%s: Failed to create figure %s!" % (
                    self.name, results['accfiglabel']),  exc_info=1)
            else:
                if show:
                    self.visplter.show_figure(results['accfiglabel'])
                return results['accfiglabel']
        else:
            plog.error("%s: Failed to create figure %s: %s" % (
                self.name, figlabel, results['status']),  exc_info=1)

    # # End Visplt Part

    def __repr__(self):
        # i = (' rawloader: %r\n pcksaver: %r\n'
        #     ' pckloader: %r\n ressaver: %r\n resfilesaver: %r\n'
        #     ' resloader: %r\n resfileloader: %r\n'
        #     ' tmplloader: %r\n visplter: %r'
        #     % (self.rawloader, self.pcksaver,
        #        self.pckloader, self.ressaver, self.resfilesaver,
        #        self.resloader, self.resfileloader,
        #        self.tmplloader, self.visplter))
        i = (' rawloader: %r\n pckloader: %r\n'
             ' resloader: %r\n resfileloader: %r\n'
             ' tmplloader: %r\n visplter: %r'
             % (self.rawloader, self.pckloader,
                self.resloader, self.resfileloader,
                self.tmplloader, self.visplter))
        return '<\n {0}.{1} object at {2},\n{3}\n>'.format(
            self.__module__, type(self).__name__, hex(id(self)), i)

    def __init__(self, path, add_desc=None, filenames_filter=None,
                 savetype='.npz', overwrite=False, Sid=False,
                 datagroups_filter=None, add_visplter='mpl::'):
        '''
        Pick up raw data or converted data in *path*,
        set processor's rawloader, pcksaver and pckloader, etc.

        Parameters
        ----------
        path: str
            path of raw data or converted data to open
        add_desc: str
            additional description of raw data
        filenames_filter: function
            function to filter filenames in rawloader
        savetype: '.npz' or '.hdf5'
            extension of pcksaver.path, default '.npz'
            when pcksaver.path isn't writable, use '.cache'
        overwrite: bool
            overwrite existing pcksaver.path file or not, default False
        Sid: bool
            If Sid is True(here), only rawloader and pcksaver will be set
            and converted to a .npz or .hdf5 file if needed. And any other
            codes(like Buzz Lightyear) will be omitted(destroyed).
            Default False.
        datagroups_filter: function
            function to filter datagroups in pckloader
        add_visplter: str
            add visplter by type *add_visplter*, default 'mpl::'
        '''
        root, ext1 = os.path.splitext(path)
        root, ext2 = os.path.splitext(root)
        if (ext2, ext1) in [('.digged', '.npz'), ('.digged', '.hdf5')]:
            # resfileloader.path
            plog.warning("This is a digged data path %s!" % path)
            path = '%s%s%s' % (root, '.converted', ext1)
            plog.warning("Try converted data path %s beside it!" % path)
            if os.path.isfile(path):
                root, ext1 = os.path.splitext(path)
                root, ext2 = os.path.splitext(root)
            else:
                plog.error("%s: Can't find path %s!" % (self.name, path))
                return
        if (ext2, ext1) in [('.converted', '.npz'), ('.converted', '.hdf5')]:
            # pckloader.path
            self.rawloader, self.pcksaver = None, None
            if Sid:
                return
            try:
                self.pckloader = get_pckloader(
                    path, datagroups_filter=datagroups_filter)
            except Exception:
                plog.error("%s: Invalid pckloader path '%s'!"
                           % (self.name, path), exc_info=1)
                return
            try:
                self.set_prefer_ressaver(ext2='digged', overwrite=overwrite)
            except Exception:
                plog.error("%s: Failed to set ressaver object!"
                           % self.name, exc_info=1)
        else:
            # rawloader.path
            try:
                self.rawloader = get_rawloader(
                    path, filenames_filter=filenames_filter)
            except Exception:
                plog.error("%s: Invalid rawloader path '%s'!"
                           % (self.name, path), exc_info=1)
                return
            try:
                self.set_prefer_pcksaver(savetype, ext2='converted')
            except Exception:
                plog.error("%s: Failed to set pcksaver object!"
                           % self.name, exc_info=1)
                return
            plog.info("Default %s data path is %s." %
                      ('converted', self.pcksaver.path))
            if Sid and self.pcksaver._extension not in ['.npz', '.hdf5']:
                return
            if os.path.isfile(self.pcksaver.path):
                if overwrite:
                    plog.warning("Remove old %s data file: %s!"
                                 % ('converted', self.pcksaver.path))
                    os.remove(self.pcksaver.path)
                    self.convert(add_desc=add_desc)
            else:
                self.convert(add_desc=add_desc)
            if Sid and self.pcksaver._extension in ['.npz', '.hdf5']:
                return
            try:
                self.pckloader = get_pckloader(
                    self.pcksaver.get_store(), datagroups_filter=datagroups_filter)
            except Exception:
                plog.error("%s: Invalid pckloader path '%s'!"
                           % (self.name, path), exc_info=1)
                return
            try:
                self.set_prefer_ressaver(ext2='digged', overwrite=overwrite)
            except Exception:
                plog.error("%s: Failed to set ressaver object!"
                           % self.name, exc_info=1)
        # set tmplloader and exporter templates, cores
        self.tmplloader = TmplLoader()
        # set visplter
        if add_visplter:
            self.visplter = get_visplter(add_visplter + path)
