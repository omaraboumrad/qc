FROM alpine:latest

# Install required packages
RUN apk add --no-cache \
    iperf3 \
    bash \
    iproute2 \
    iputils \
    curl

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
