// !! This file has been generated by dnsdist-rules-generator.py, do not edit by hand!!
std::shared_ptr<DNSResponseAction> getAllowResponseAction();
std::shared_ptr<DNSResponseAction> getDelayResponseAction(uint32_t msec);
std::shared_ptr<DNSResponseAction> getDropResponseAction();
std::shared_ptr<DNSResponseAction> getLogResponseAction(const std::string& file_name, bool append, bool buffered, bool verbose_only, bool include_timestamp);
std::shared_ptr<DNSResponseAction> getLuaFFIPerThreadResponseAction(const std::string& code);
std::shared_ptr<DNSResponseAction> getSetExtendedDNSErrorResponseAction(uint16_t info_code, const std::string& extra_text);
std::shared_ptr<DNSResponseAction> getSetReducedTTLResponseAction(uint8_t percentage);
std::shared_ptr<DNSResponseAction> getSetSkipCacheResponseAction();
std::shared_ptr<DNSResponseAction> getSetTagResponseAction(const std::string& tag, const std::string& value);
std::shared_ptr<DNSResponseAction> getSNMPTrapResponseAction(const std::string& reason);
std::shared_ptr<DNSResponseAction> getTCResponseAction();