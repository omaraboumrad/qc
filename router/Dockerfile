FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install required packages for traffic shaping and monitoring
RUN apt-get update && apt-get install -y \
    iproute2 \
    iptables \
    iperf3 \
    curl \
    jq \
    net-tools \
    iputils-ping \
    procps \
    kmod \
    && rm -rf /var/lib/apt/lists/*

# Create directories for scripts and config
RUN mkdir -p /scripts /config/rules

# Copy scripts and configuration
COPY entrypoint.sh /entrypoint.sh
COPY scripts/*.sh /scripts/
COPY config/default_rules.json /config/default_rules.json

# Make scripts executable
RUN chmod +x /entrypoint.sh /scripts/*.sh

# Expose iperf3 server port
EXPOSE 5201

CMD ["/entrypoint.sh"]
