      *================================================================
      * INTACCR - MONTHLY INTEREST ACCRUAL BATCH STEP
      *
      * Ground-truth oracle for MainframeGhost. Compiled with GnuCOBOL
      * (cobc -x -fsign=EBCDIC) and run against the same seeded corpus
      * the Python engine and every candidate service are tested on.
      *
      * The record layout comes from copybooks/INTACCR.cpy. There is no
      * ROUNDED phrase, so COBOL truncates the quotient toward zero.
      *
      * ACCTIN  (line sequential, 25 chars per line)
      *   KEY X(8) | BALANCE S9(9)V99 SIGN LEADING SEPARATE | RATE 9V9(4)
      * ACCTOUT (fixed 25-byte binary records)
      *   KEY X(8) | INTEREST S9(9)V99 COMP-3 | NEW-BALANCE S9(9)V99
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. INTACCR.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-IN  ASSIGN TO "ACCTIN"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT ACCT-OUT ASSIGN TO "ACCTOUT"
               ORGANIZATION IS SEQUENTIAL.

       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-IN.
       01  IN-REC.
           05  IN-KEY              PIC X(8).
           05  IN-BALANCE          PIC S9(9)V99
                                   SIGN IS LEADING SEPARATE.
           05  IN-RATE             PIC 9V9(4).

       FD  ACCT-OUT.
       01  OUT-REC.
           05  OUT-KEY             PIC X(8).
           05  OUT-INTEREST        PIC S9(9)V99 COMP-3.
           05  OUT-NEW-BALANCE     PIC S9(9)V99.

       WORKING-STORAGE SECTION.
           COPY INTACCR.
       01  WS-EOF                  PIC X VALUE "N".
       01  WS-COUNT                PIC 9(9) VALUE ZERO.

       PROCEDURE DIVISION.
       MAIN-PARA.
           OPEN INPUT ACCT-IN
                OUTPUT ACCT-OUT
           PERFORM UNTIL WS-EOF = "Y"
               READ ACCT-IN
                   AT END
                       MOVE "Y" TO WS-EOF
                   NOT AT END
                       PERFORM ACCRUE-PARA
               END-READ
           END-PERFORM
           CLOSE ACCT-IN ACCT-OUT
           DISPLAY "INTACCR RECORDS PROCESSED: " WS-COUNT
           STOP RUN.

       ACCRUE-PARA.
           MOVE IN-KEY      TO ACCT-KEY
           MOVE IN-BALANCE  TO ACCT-BALANCE
           MOVE IN-RATE     TO ACCT-ANNUAL-RATE
           COMPUTE WS-INTEREST =
               (ACCT-BALANCE * ACCT-ANNUAL-RATE) / 12
           COMPUTE WS-NEW-BALANCE = ACCT-BALANCE + WS-INTEREST
           MOVE ACCT-KEY       TO OUT-KEY
           MOVE WS-INTEREST    TO OUT-INTEREST
           MOVE WS-NEW-BALANCE TO OUT-NEW-BALANCE
           WRITE OUT-REC
           ADD 1 TO WS-COUNT.
