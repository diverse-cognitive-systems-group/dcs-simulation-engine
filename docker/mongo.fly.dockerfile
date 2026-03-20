# syntax=docker/dockerfile:1

FROM mongo:8.0

EXPOSE 27017

CMD ["mongod", "--bind_ip_all", "--ipv6", "--noauth"]
