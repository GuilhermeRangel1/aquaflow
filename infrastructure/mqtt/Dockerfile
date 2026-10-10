FROM eclipse-mosquitto:2@sha256:38c0da4f2ef84284d47b3b3eeea1cb3bdeabe81ee10caf0cd5c5ff61ee3ea408

COPY mosquitto.conf /mosquitto/config/mosquitto.conf
COPY acl /mosquitto/config/acl
COPY entrypoint.sh /usr/local/bin/aquaflow-mosquitto
USER root
RUN chmod 755 /usr/local/bin/aquaflow-mosquitto
ENTRYPOINT ["/usr/local/bin/aquaflow-mosquitto"]
