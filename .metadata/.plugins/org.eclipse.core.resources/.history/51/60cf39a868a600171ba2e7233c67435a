package nl.xupwup.Util;

import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;

/**
 *
 * @author Rick
 */
public class CountingOutputStream extends FilterOutputStream{

    private long index = 0;
    
    public CountingOutputStream(OutputStream out) {
        super(out);
    }

    public void reset(){
        setIndex(0);
    }
    
    public long getIndex(){
        return index;
    }
    public void setIndex(long i){
        index = i;
    }
    
    @Override
    public void write(byte[] b) throws IOException {
        out.write(b);
        index += b.length;
    }

    @Override
    public void write(int b) throws IOException {
        out.write(b);
        index += 1;
    }

    @Override
    public void write(byte[] b, int off, int len) throws IOException {
        out.write(b, off, len);
        index += len;
    }

    @Override
    public void flush() throws IOException {
        out.flush();
    }

    @Override
    public void close() throws IOException {
        out.close(); //To change body of generated methods, choose Tools | Templates.
    }
    
}
