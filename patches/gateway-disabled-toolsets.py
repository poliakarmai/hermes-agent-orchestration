        # Multi-tenant: profile-specific disabled_toolsets (fail-closed)
        _profile_restrictive_default = ["terminal", "file", "cronjob", "delegation"]
        try:
            tg_cfg = user_config.get("telegram", {})
            channel_profiles = tg_cfg.get("channel_profiles", {})
            chat_id = str(source.chat_id or "")
            if chat_id and chat_id in channel_profiles:
                profile_name = channel_profiles[chat_id]
                profile_config_path = _hermes_home / "profiles" / profile_name / "config.yaml"
                if profile_config_path.exists():
                    import yaml
                    with open(profile_config_path) as pf:
                        profile_cfg = yaml.safe_load(pf) or {}
                    profile_disabled = (profile_cfg.get("agent") or {}).get("disabled_toolsets") or []
                    if profile_disabled:
                        _base = list(disabled_toolsets) if disabled_toolsets else []
                        disabled_toolsets = list(set(_base + profile_disabled))
                    # MCP isolation: tenants must not inherit admin's global MCP servers
                    _admin_profiles = {"poliakarm", "default"}
                    if profile_name not in _admin_profiles:
                        _global_mcp = set((user_config.get("mcp_servers") or {}).keys())
                        _profile_mcp = set((profile_cfg.get("mcp_servers") or {}).keys())
                        _mcp_disable = _global_mcp - _profile_mcp
                        if _mcp_disable:
                            _base2 = list(disabled_toolsets) if disabled_toolsets else []
                            disabled_toolsets = list(set(_base2 + list(_mcp_disable)))
                    # C7 fix: set tenant user for terminal isolation
                    _tenant_name = (profile_cfg.get("profile") or {}).get("tenant_name")
                    if _tenant_name:
                        os.environ["HERMES_TENANT_USER"] = "hermes-" + _tenant_name
                        _sandbox = (profile_cfg.get("profile") or {}).get("sandbox")
                        if _sandbox:
                            os.environ["HERMES_TENANT_SANDBOX"] = _sandbox
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Profile %s config failed to load (%s). Applying restrictive defaults: %s",
                profile_name, exc, _profile_restrictive_default,
            )
            disabled_toolsets = list(
                set((disabled_toolsets or []) + _profile_restrictive_default)
            )
