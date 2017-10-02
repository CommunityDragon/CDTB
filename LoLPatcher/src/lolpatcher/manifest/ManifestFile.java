package lolpatcher.manifest;

/**
 *
 * @author Rick
 */
public class ManifestFile{
    public final String release;
    public final int releaseInt;
    public final String name;
    public String path;
    public final byte[] checksum;
    public final int sizeCompressed;
    public final int sizeUncompressed; // use this value instead of size when type is 6

    @Override
    public String toString() {
        return path + name + " " +release + " type:" + fileType + " u2:" + sizeUncompressed + " u3:"+unknown3 + " u4:" + unknown4;
    }



    /**
     * 6 = uncompressed - archive
     * 22 = compressed - archive
     * 5 = managedfile
     * greater than 0 = compressed
     * 0 = normal file
     * 2 = compressed file
     * 4 = copy to sln?
     */
    public final int fileType;
    
    public final int unknown3;
    public final int unknown4;

    public ManifestFile(String release, int releaseInt, String name, byte[] checksum, int sizeCompressed,
            int fileType, int sizeUncompressed, int unknown3, int unknown4) {
        this.release = release;
        this.releaseInt = releaseInt;
        this.name = name;
        this.checksum = checksum;
        this.sizeCompressed = sizeCompressed;
        this.fileType = fileType;
        if(fileType != 0 && fileType != 2 && fileType != 5 && fileType != 6 && fileType != 22 && fileType != 4){
            System.out.println("Hmm... fileType = " + fileType + " (" + name + ")");
        }
        this.sizeUncompressed = sizeUncompressed;
        this.unknown3 = unknown3;
        this.unknown4 = unknown4;
    }
}