def select_modulation(snr_db):
    """
    Select modulation based on measured SNR.
    """

    if snr_db >= 15:
        return "16-QAM"

    elif snr_db >= 8:
        return "QPSK"

    elif snr_db >= 0:
        return "BPSK"

    else:
        return "NO TRANSMISSION"


if __name__ == "__main__":
    test_values = [23, 11, 5, -3]

    for snr in test_values:
        modulation = select_modulation(snr)
        print(f"SNR: {snr:>5} dB | Modulation: {modulation}")
