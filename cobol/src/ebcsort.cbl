      *================================================================
      * EBCSORT - SORT ACCOUNT KEYS IN EBCDIC COLLATING SEQUENCE
      *
      * Ground truth for the mainframe SORT order. On z/OS the native
      * sequence is EBCDIC; GnuCOBOL runs on an ASCII machine, so the
      * EBCDIC alphabet is named explicitly in COLLATING SEQUENCE.
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. EBCSORT.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SPECIAL-NAMES.
           ALPHABET EBCDIC-SEQ IS EBCDIC.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT KEYS-IN  ASSIGN TO "KEYSIN"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT KEYS-OUT ASSIGN TO "KEYSOUT"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SORT-WK  ASSIGN TO "SORTWK".

       DATA DIVISION.
       FILE SECTION.
       FD  KEYS-IN.
       01  KI-REC                  PIC X(8).
       FD  KEYS-OUT.
       01  KO-REC                  PIC X(8).
       SD  SORT-WK.
       01  SW-REC.
           05  SW-KEY              PIC X(8).

       PROCEDURE DIVISION.
       MAIN-PARA.
           SORT SORT-WK
               ON ASCENDING KEY SW-KEY
               COLLATING SEQUENCE IS EBCDIC-SEQ
               USING KEYS-IN
               GIVING KEYS-OUT
           STOP RUN.
