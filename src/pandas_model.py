#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PyQt5.QtCore import Qt, QAbstractTableModel, QVariant, QSize
import numpy as np
import pandas as pd


class ModelDataFrame(QAbstractTableModel):
    # class object to override QAbstractTableModel that creates a custom model
    # for returning cells from a dataframe to present in PyQt5 - ( specifically QTableView).
    def __init__(self, df, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self._df = np.array(df.values)
        self.original_df = df.copy()

        self._cols = df.columns
        self.r, self.c = np.shape(self._df)

    def rowCount(self, parent=None):
        return self.r

    def columnCount(self, parent=None):
        return self.c

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return QVariant()

        if not index.isValid():
            return QVariant()

        return QVariant(str(self._df[index.row(), index.column()]))

    def setData(self, index, value, role):
        # vertical and horizontal data
        row = self._df[index.row()]
        col = self._df[index.column()]

        if hasattr(value, 'toPyObject'):
            value = value.toPyObject()
        else:
            dtype = self._df.dtype
            if dtype != object:
                value = None if value == '' else dtype.type(value)
        table_row = row[0]-1
        table_col = col[0]-1
        self._df[table_row, table_col] = value
        if role == Qt.EditRole and self.reason == 'Read':
            column_name = self.original_df.columns[table_col]
            self.original_df.loc[table_row, column_name] = value

            my_df = pd.DataFrame(self._df)
            my_df.columns = self.original_df.columns
            self.conSig.dataChanged.emit(table_row, table_col, my_df)
        return True

    def headerData(self, p_int, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._cols[p_int]
            elif orientation == Qt.Vertical:
                return p_int
        return None