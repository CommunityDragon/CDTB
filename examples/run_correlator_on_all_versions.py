from clientcorrelator import clientcorrelator


def main():
    vc = clientcorrelator.get_version_correlations(["0.0.0.108"])
    print(vc)


if __name__ == "__main__":
    main()