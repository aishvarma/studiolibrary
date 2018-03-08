# This library is free software: you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
# You should have received a copy of the GNU Lesser General Public
# License along with this library. If not, see <http://www.gnu.org/licenses/>.

import os
import logging

import studiolibrary

import studioqt
from studioqt import QtCore

__all__ = [
    "LibraryModel",
]

logger = logging.getLogger(__name__)


class LibraryModel(QtCore.QObject):

    ColumnLabels = ["Icon", "Name", "Path", "Type", "Category", "Modified"]
    DatabasePath = "{path}/.studiolibrary/database.json"

    EnableWatcher = False
    WatcherRepeatRate = 1  # in seconds

    dataChanged = QtCore.Signal()
    fileChanged = QtCore.Signal()

    def __init__(self, path, *args):
        QtCore.QObject.__init__(self, *args)

        self._path = None
        self._data = {}
        self._items = []
        self._mtime = None
        self._watcher = None

        self.setPath(path)
        self.setDirty(True)
        self.setWatcherEnabled(self.EnableWatcher)

    def path(self):
        """
        Return the disc location of the db.

        :rtype: str
        """
        return self._path

    def setPath(self, path):
        """
        Set the disc location of the db.

        :type path: str
        """
        self._path = path

    def databasePath(self):
        """
        Return the path to the database.
        
        :rtype: str 
        """
        return studiolibrary.formatPath(self.DatabasePath, path=self.path())

    def setWatcherEnabled(self, enable, repeatRate=None):
        """
        Enable a watcher that will trigger the database changed signal.

        :type enable: bool
        :type repeatRate: int
        :rtype: None
        """
        if enable:
            self.startWatcher(repeatRate=repeatRate)
        else:
            self.stopWatcher()

    def startWatcher(self, repeatRate=None):
        """
        Create and start a file system watcher for the current database. 

        :type repeatRate: int
        :rtype: None 
        """
        self.stopWatcher()

        repeatRate = repeatRate or self.WatcherRepeatRate

        self._watcher = studioqt.InvokeRepeatingThread(repeatRate)
        self._watcher.triggered.connect(self._fileChanged)
        self._watcher.start()

    def stopWatcher(self):
        """
        Stop watching the current database for changes.
        
        :rtype: None 
        """
        if self._watcher:
            self._watcher.terminate()
            self._watcher = None

    def _fileChanged(self):
        """
        Triggered when the watcher has reached it's repeat rate.

        :rtype: None
        """
        if self.isDirty():
            self.setDirty(False)
            self.fileChanged.emit()

    def mtime(self):
        """
        Return the time of last modification of db.

        :rtype: float or None
        """
        path = self.databasePath()
        mtime = None

        if os.path.exists(path):
            mtime = os.path.getmtime(path)

        return mtime

    def setDirty(self, value):
        """
        Update the database object with the current timestamp of the db path.

        :rtype: None
        """
        if value:
            self._mtime = None
        else:
            self._mtime = self.mtime()

    def isDirty(self):
        """
        Return True if the database has changed on disc.

        :rtype: bool
        """
        return self._mtime != self.mtime()

    def read(self):
        """
        Read the database from disc and return a dict object.

        :rtype: dict
        """
        if self.isDirty():
            self._data = studiolibrary.readJson(self.databasePath())
            self.setDirty(False)

        return self._data

    def save(self, data):
        """
        Write the given dict object to the database on disc.

        :type data: dict
        :rtype: None
        """
        studiolibrary.saveJson(self.databasePath(), data)

    def sync(self):
        """
        Sync any data that might be out of date. 
        
        :rtype: None 
        """
        data = self.read()

        isDirty = False

        for path in data.keys():
            if not os.path.exists(path):
                isDirty = True
                del data[path]

        items = studiolibrary.findItems(self.path())

        for item in items:
            path = item.path()
            if item.path() not in data:
                isDirty = True
                data[path] = {}

        if isDirty:
            self.save(data)
            self.dataChanged.emit()

    def columnLabels(self):
        """
        Return the header labels for the item model.
        
        :rtype: list[str] 
        """
        return self.ColumnLabels

    def addItem(self, item, data=None):
        """
        Add the given item to the database.    
    
        :type item: studiolibrary.LibraryItem
        :type data: dict or None
        :rtype: None 
        """
        self.addItems([item], data)

    def addItems(self, items, data=None):
        """
        Add the given items to the database.
        
        :type items: list[studiolibrary.LibraryItem]
        :type data: dict or None
        :rtype: None 
        """
        logger.info("Add items %s", items)

        paths = [item.path() for item in items]

        self.addPaths(paths, data)

        self.dataChanged.emit()

    def copyItems(self, items, dst):
        """
        Copy the given items to the destination path and update the database.
        
        :type items: list[studiolibrary.LibraryItem]
        :type dst: str
        :rtype: None 
        """
        logger.info("Copy items to %s", dst)

        for item in items:
            path = self.copyPath(item.path(), dst)
            item.setPath(path)

        self.dataChanged.emit()

    def renameItems(self, items, dst):
        """
        Rename the given items to the given name and update the database.
        
        :type items: list[studiolibrary.LibraryItem]
        :type dst: str
        :rtype: None 
        """
        logger.info("Rename items to %s", dst)

        for item in items:
            dst = self.renamePath(item.path(), dst)
            item.setPath(dst)

        self.dataChanged.emit()

    def removeItems(self, items):
        """
        Remove the given items from disc and update the database.
        
        :type items: list[studiolibrary.LibraryItem]
        :rtype: None 
        """
        logger.info("Remove items %s", items)

        paths = [item.path() for item in items]
        self.removePaths(paths)

        self.dataChanged.emit()

    def createItems(self, *args, **kwargs):
        """
        Create items by walking the given path.

        :rtype: list[studiolibrary.LibraryItem] 
        """
        # Check if the database has changed since the last read call
        if self.isDirty():

            items = studiolibrary.findItems(self.path(), *args, **kwargs)
            self._items = list(items)

            self.loadItemData(self._items)

        return self._items

    def saveItemData(self, items, columns=None):
        """
        Save the given items and their data to the database.

        :type columns: list[str]
        :type items: list[studiolibrary.LibraryItem]
        """
        data = {}
        columns = columns or ["Custom Order"]

        for item in items:
            path = item.path()
            data.setdefault(path, {})

            for column in columns:
                value = item.text(column)
                data[path].setdefault(column, value)

        studiolibrary.updateJson(self.databasePath(), data)

    def loadItemData(self, items):
        """
        Set the item data for all the current items.

        :type items: list[studiolibrary.LibraryItem]
        :rtype: None
        """
        data = self.read()

        for item in items:
            key = item.id()

            if key in data:

                for column in data[key]:
                    value = data[key].get(column)

                    if value is not None:
                        item.setText(column, value)

                item.updateData()

    def addPaths(self, paths, data=None):
        """
        Add the given path and the given data to the database.    
    
        :type paths: list[str]
        :type data: dict or None
        :rtype: None 
        """
        data = data or {}
        self.updatePaths(paths, data)

    def updatePaths(self, paths, data):
        """
        Update the given paths with the given data in the database.

        :type paths: list[str]
        :type data: dict
        :rtype: None
        """
        data_ = self.read()
        paths = studiolibrary.normPaths(paths)

        for path in paths:
            if path in data_:
                data_[path].update(data)
            else:
                data_[path] = data

        self.save(data_)

    def copyPath(self, src, dst):
        """
        Remove the given path from the database.

        :type src: str
        :type dst: str
        :rtype: str
        """
        path = studiolibrary.copyPath(src, dst)
        self.addPaths([path])
        return path

    def renamePath(self, src, name):
        """
        Remove the given path from the database.

        :type src: str
        :type name: str
        :rtype: str
        """
        dst = studiolibrary.renamePath(src, name)
        studiolibrary.renamePathInFile(self.databasePath(), src, dst)
        return dst

    def removePath(self, path):
        """
        Remove the given path from the database.

        :type path: str
        :rtype: None
        """
        studiolibrary.removePath(path)
        self.removePaths([path])

    def removePaths(self, paths):
        """
        Remove the given paths from the database.

        :type paths: list[str]
        :rtype: None
        """
        data = self.read()

        paths = studiolibrary.normPaths(paths)

        for path in paths:
            if path in data:
                del data[path]

        self.save(data)
