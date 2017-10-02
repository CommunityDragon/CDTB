package nl.xupwup.Util;

public class RoundFloat {
    public static double round(double d, int decimals){
        return Math.round(d * Math.pow(10, decimals)) / Math.pow(10, decimals);
    }
}
