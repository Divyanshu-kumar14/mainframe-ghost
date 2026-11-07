      *================================================================
      * INTACCR  -  CORE BANKING INTEREST ACCRUAL RECORD  (1968 / REV 1983)
      *================================================================
       01  ACCOUNT-RECORD.
           05  ACCT-KEY            PIC X(8).
           05  ACCT-STATUS         PIC X(1).
           05  ACCT-BRANCH         PIC S9(4) COMP SYNC.
           05  ACCT-OPEN-DATE      PIC 9(8).
           05  ACCT-OPEN-PARTS REDEFINES ACCT-OPEN-DATE.
               10  ACCT-OPEN-YYYY  PIC 9(4).
               10  ACCT-OPEN-MM    PIC 9(2).
               10  ACCT-OPEN-DD    PIC 9(2).
           05  ACCT-LEDGER-SEQ     PIC S9(9) COMP SYNC.
           05  ACCT-BALANCE        PIC S9(9)V99 COMP-3.
           05  ACCT-ANNUAL-RATE    PIC 9V9(4).
           05  WS-INTEREST         PIC S9(9)V99 COMP-3.
           05  WS-NEW-BALANCE      PIC S9(9)V99.
