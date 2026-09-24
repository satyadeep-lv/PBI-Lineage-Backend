import truststore

# Verify TLS against the operating system's trust store rather than certifi's
# bundle. Corporate proxies (Zscaler, CrowdStrike Falcon on this estate) re-sign
# outbound TLS with a root that is installed in the OS store but not in certifi,
# so without this every httpx/requests call through them -- litellm's model call
# and its tokenizer download included -- fails with CERTIFICATE_VERIFY_FAILED.
# Done here, in the package root, so it runs before any SSL context is created
# whatever the entrypoint.
truststore.inject_into_ssl()
