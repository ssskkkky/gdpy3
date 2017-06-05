# -*- coding: utf-8 -*-

# Copyright (c) 2017 shmilee

'''
This module provides the :class:`GFigure`, which contains
all the plot elements, calculation results, figure methods.
'''

import os
import logging

from . import tools
from .enginelib import engine_available, default_engine, get_engine

__all__ = ['GFigure']

log = logging.getLogger('gdp')


class GFigure(object):
    '''
    A figure-like object with lazy-plotting of figures.

    Attributes
    ----------
    name: str
    group: str
    Name: str
        *group*-*name*
    gtcdataobj: :class:`gdpy3.read.readnpz.ReadNpz` instance
        a dictionary-like object of *gtcdatafile*
    figurekeys: list
        physical quantities in *gtcdataobj* used in this figure
    figurestructure: dict
        dict container for all plot elements
    calculation: dict
        dict container for all calculation results
    engine: name of the plot engine
        default 'matplotlib'
    nginp: instance of :class:`gdpy3.plot.enginelib.base.Engine`
        plot engine, set by *engine*
    figurestyle: list
        mplstyles used in *figurestructure*
    figure: Figure instance
        the real figure

    Parameters
    ----------
    name, group, gtcdataobj, figurekeys
    engine, figurestyle
    '''
    __slots__ = ['name', 'group', '__gtcdataobj', '__figurekeys',
                 '__figurestructure', '__calculation',
                 '__engine', '__nginp',
                 '__figurestyle', 'figure']

    def __init__(self, name, group, gtcdataobj, figurekeys,
            engine=default_engine,
            figurestyle=[]):
        self.name = name
        self.group = group
        self.gtcdataobj = gtcdataobj
        self.figurekeys = figurekeys
        self.figurestructure = {}
        self.calculation = {}
        self.engine = engine
        self.figurestyle = figurestyle
        self.figure = None

    @property
    def Name(self):
        return self. group + '-' + self.name

    @property
    def gtcdataobj(self):
        return self.__gtcdataobj

    @gtcdataobj.setter
    def gtcdataobj(self, dataobj):
        if tools.is_dictobj(dataobj):
            self.__gtcdataobj = dataobj
        else:
            raise ValueError("'gtcdataobj' must be a ReadNpz instance."
                             " Not %s." % type(dataobj))

    @property
    def figurekeys(self):
        return self.__figurekeys

    @figurekeys.setter
    def figurekeys(self, keys):
        if not isinstance(keys, list):
            raise ValueError("'figurekeys' must be a list."
                             " Not %s." % type(keys))
        else:
            if tools.in_dictobj(self.gtcdataobj, *keys):
                self.__figurekeys = keys
            else:
                raise ValueError("Some keys are invalid!")

    @property
    def figurestructure(self):
        return self.__figurestructure

    @figurestructure.setter
    def figurestructure(self, structure):
        if isinstance(structure, dict):
            self.__figurestructure = structure
        else:
            log.error("'FigureStructure' must be a dict."
                             " Not %s." % type(structure))

    @property
    def calculation(self):
        return self.__calculation

    @calculation.setter
    def calculation(self, calresult):
        if isinstance(calresult, dict):
            self.__calculation = calresult
        else:
            log.error("'calculation result' must be a dict."
                             " Not %s." % type(calresult))

    @property
    def engine(self):
        return self.__engine

    @engine.setter
    def engine(self, eng):
        if eng in engine_available:
            self.__engine = eng
        else:
            log.error("Plot engine '%s' not found in '%s'! Use default '%s'!"
                  % (eng, engine_available, default_engine))
            self.__engine = default_engine
        self.__nginp = get_engine(self.__engine)

    @property
    def nginp(self):
        return self.__nginp

    @property
    def figurestyle(self):
        return self.__figurestyle

    @figurestyle.setter
    def figurestyle(self, styles):
        if not isinstance(styles, list):
            log.error("'figurestyle' must be a list. Not %s." % type(styles))
            self.__figurestyle = []
        else:
            self.__figurestyle = styles

    def calculate(self, **kwargs):
        '''
        Get the FigureStructure and calculation results.
        Define this function in derived class.
        '''
        log.error('Define this function in derived class.')
        raise

    def draw(self, num=None, **kwargs):
        '''
        convert *figurestructure* to Figure instance *figure*

        Parameters
        ----------
        num: integer or string
            pass to *nginp*.figure_factory method
        kwargs: pass to *calculate* method
        '''
        self.close()
        if not self.figurestructure:
            self.calculate(**kwargs)
        log.debug("Drawing figure '%s' ..." % self.Name)
        self.figure = self.nginp.figure_factory(self.figurestructure, num=num)

    def plot(self, **kwargs):
        '''
        plot this figure -- synonym for :meth:`draw`.
        '''
        self.draw(**kwargs)

    def close(self):
        '''
        Close this figure
        '''
        if self.figure:
            self.nginp.close(self.figure)
        self.figure = None

    def show(self):
        '''
        display this figure
        '''
        if not self.figure:
            self.plot()
        self.nginp.show(self.figure)
