package nl.xupwup.Util;

import java.io.EOFException;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.RandomAccessFile;

/**
 *
 * @author Rick
 */
public class FileSliceInputStream extends InputStream{

    long length;

    RandomAccessFile in;
    public FileSliceInputStream(File f, long offset, long length) throws IOException{
        in = new RandomAccessFile(f, "r");
        in.seek(offset);
        this.length = length;
    }

    @Override
    public void close() throws IOException {
        in.close();
    }

    @Override
    public int read() throws IOException {
        if(length > 0){
            length--;
            return in.read();
        }else{
            return -1;
        }
    }

    @Override
    public int read(byte[] b, int off, int len) throws IOException {
        if(length <= 0){
            return -1;
        }
        int read = in.read(b, off, (int) Math.min(length, len));
        if(read == -1){
            throw new EOFException("Unexpected end of file");
        }
        length -= read;
        return read;
    }

    @Override
    public int read(byte[] b) throws IOException {
        return read(b, 0, b.length);
    }
}