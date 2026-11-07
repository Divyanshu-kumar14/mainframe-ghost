# GnuCOBOL 3.1.2 build/run image for the MainframeGhost oracle.
# The image only compiles and runs the COBOL programs in cobol/src; it has no
# network access at run time (engine/cobol_oracle.py passes --network none).
FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends gnucobol3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /work
