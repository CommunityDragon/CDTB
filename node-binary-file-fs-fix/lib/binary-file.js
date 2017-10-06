'use strict';

const BINARY_LENGTH = {
  'Int8': 1,
  'UInt8': 1,
  'Int16': 2,
  'UInt16': 2,
  'Int32': 4,
  'UInt32': 4,
  'Float': 4,
  'Double': 8
};

const fs_fix = require('graceful-fs');

const denodeify = require('denodeify');
const fsOpen = denodeify(fs_fix.open);
const fsRead = denodeify(fs_fix.read);
const fsFstat = denodeify(fs_fix.fstat);
const fsClose = denodeify(fs_fix.close);
const fsWrite = denodeify(fs_fix.write);

class BinaryFile {
  constructor (path, mode, littleEndian) {
    littleEndian = littleEndian || false;
    this.path = path;
    this.mode = mode;
    this.endianness = littleEndian ? 'LE' : 'BE';
    this.cursor = 0;
  }

  // Misc

  open () {
    return new Promise((resolve) => {
      fsOpen(this.path, this.mode).then((fd) => {
        this.fd = fd;
        resolve();
      });
    });
  }

  size () {
    return new Promise((resolve) => {
      fsFstat(this.fd).then((stat) => {
        resolve(stat.size);
      });
    });
  }

  seek (position) {
    this.cursor = position;
    return position;
  }

  tell () {
    return this.cursor;
  }

  close () {
    return new Promise((resolve) => {
      fsClose(this.fd, () => {
        resolve();
      });
    });
  }

  // Read

  read (length, position) {
    return new Promise((resolve) => {
      const buffer = new Buffer(length);
      fsRead(this.fd, buffer, 0, buffer.length, position || this.cursor).then((bytesRead) => {
        if (typeof position === 'undefined') this.cursor += bytesRead;
        resolve(buffer);
      });
    });
  }

  _readNumericType (type, position) {
    return new Promise((resolve) => {
      const length = BINARY_LENGTH[type];
      this.read(length, position).then((buffer) => {
        const value = buffer['read' + type + (length > 1 ? this.endianness : '')](0);
        resolve(value);
      });
    });
  }

  readInt8 (position) {
    return this._readNumericType('Int8', position);
  }

  readUInt8 (position) {
    return this._readNumericType('UInt8', position);
  }

  readInt16 (position) {
    return this._readNumericType('Int16', position);
  }

  readUInt16 (position) {
    return this._readNumericType('UInt16', position);
  }

  readInt32 (position) {
    return this._readNumericType('Int32', position);
  }

  readUInt32 (position) {
    return this._readNumericType('UInt32', position);
  }

  readFloat (position) {
    return this._readNumericType('Float', position);
  }

  readDouble (position) {
    return this._readNumericType('Double', position);
  }

  readString (length, position) {
    return new Promise((resolve) => {
      this.read(length, position).then((buffer) => {
        const value = buffer.toString();
        resolve(value);
      });
    });
  }

  // Write

  write (buffer, position) {
    return new Promise((resolve) => {
      fsWrite(this.fd, buffer, 0, buffer.length, position || this.cursor).then((bytesWritten) => {
        if (typeof position === 'undefined') this.cursor += bytesWritten;
        resolve(bytesWritten);
      });
    });
  }

  _writeNumericType (value, type, position) {
    const length = BINARY_LENGTH[type];
    const buffer = new Buffer(length);
    buffer['write' + type + (length > 1 ? this.endianness : '')](value, 0);
    return this.write(buffer, position);
  }

  writeInt8 (value, position) {
    return this._writeNumericType(value, 'Int8', position);
  }

  writeUInt8 (value, position) {
    return this._writeNumericType(value, 'UInt8', position);
  }

  writeInt16 (value, position) {
    return this._writeNumericType(value, 'Int16', position);
  }

  writeUInt16 (value, position) {
    return this._writeNumericType(value, 'UInt16', position);
  }

  writeInt32 (value, position) {
    return this._writeNumericType(value, 'Int32', position);
  }

  writeUInt32 (value, position) {
    return this._writeNumericType(value, 'UInt32', position);
  }

  writeFloat (value, position) {
    return this._writeNumericType(value, 'Float', position);
  }

  writeDouble (value, position) {
    return this._writeNumericType(value, 'Double', position);
  }

  writeString (value, position) {
    const buffer = new Buffer(value);
    return this.write(buffer, position);
  }
}

module.exports = BinaryFile;
