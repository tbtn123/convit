-- public.access_keys definition

-- Drop table

-- DROP TABLE public.access_keys;

CREATE TABLE public.access_keys ( id text DEFAULT gen_random_uuid()::text NOT NULL, discord_id text NOT NULL, key_hash text NOT NULL, created_at timestamp DEFAULT now() NOT NULL, last_used timestamp NULL, CONSTRAINT access_keys_key_hash_key UNIQUE (key_hash), CONSTRAINT access_keys_pkey PRIMARY KEY (id));
CREATE INDEX idx_access_keys_discord_id ON public.access_keys USING btree (discord_id);
CREATE INDEX idx_access_keys_key_hash ON public.access_keys USING btree (key_hash);


-- public.broadcast definition

-- Drop table

-- DROP TABLE public.broadcast;

CREATE TABLE public.broadcast ( guild_id int8 NOT NULL, "text" text NULL, CONSTRAINT broadcast_pkey PRIMARY KEY (guild_id));


-- public.farm_info definition

-- Drop table

-- DROP TABLE public.farm_info;

CREATE TABLE public.farm_info ( farm_id int8 NOT NULL, input_id int8 NOT NULL, duration int4 NOT NULL, output_id int8 NOT NULL, output_amount int4 NOT NULL, id serial4 NOT NULL, CONSTRAINT farm_info_pk PRIMARY KEY (id));


-- public.farm_sessions definition

-- Drop table

-- DROP TABLE public.farm_sessions;

CREATE TABLE public.farm_sessions ( user_id int8 NOT NULL, farm_id int8 NOT NULL, created_at timestamptz DEFAULT CURRENT_TIMESTAMP NULL, duration int4 NOT NULL, finished_at timestamptz NULL, session_id serial4 NOT NULL);


-- public.giftcode_users definition

-- Drop table

-- DROP TABLE public.giftcode_users;

CREATE TABLE public.giftcode_users ( id serial4 NOT NULL, user_id int8 NOT NULL, giftcode_id int4 NOT NULL);


-- public.giftcodes definition

-- Drop table

-- DROP TABLE public.giftcodes;

CREATE TABLE public.giftcodes ( id serial4 NOT NULL, code text NOT NULL, uses int4 NOT NULL, prize int4 NOT NULL);


-- public.global_info definition

-- Drop table

-- DROP TABLE public.global_info;

CREATE TABLE public.global_info ( coins int8 DEFAULT 0 NULL);


-- public.global_mining_config definition

-- Drop table

-- DROP TABLE public.global_mining_config;

CREATE TABLE public.global_mining_config ( min_depth int4 NOT NULL, max_depth int4 NOT NULL, probability float4 NOT NULL, item_id int4 NULL, CONSTRAINT global_loot_config_probability_check CHECK (((probability >= (0)::double precision) AND (probability <= (1)::double precision))));


-- public.global_shop definition

-- Drop table

-- DROP TABLE public.global_shop;

CREATE TABLE public.global_shop ( pool_id int4 NOT NULL, price int4 NOT NULL, stock int4 NULL);


-- public.guild_config definition

-- Drop table

-- DROP TABLE public.guild_config;

CREATE TABLE public.guild_config ( guild_id int8 NOT NULL, api_key text NULL, prefix varchar NULL, allow_rob bool DEFAULT true NOT NULL, locale text NULL, transfer_tax_rate float4 DEFAULT 0.0 NULL, CONSTRAINT server_config_pkey PRIMARY KEY (guild_id));


-- public.guilds definition

-- Drop table

-- DROP TABLE public.guilds;

CREATE TABLE public.guilds ( id int8 NOT NULL, coins int8 DEFAULT 0 NOT NULL, CONSTRAINT guilds_pk PRIMARY KEY (id));


-- public.inventory definition

-- Drop table

-- DROP TABLE public.inventory;

CREATE TABLE public.inventory ( id int8 NOT NULL, item_id int4 NOT NULL, quantity int4 NULL, CONSTRAINT inventory_pkey PRIMARY KEY (id, item_id));


-- public.item_effects definition

-- Drop table

-- DROP TABLE public.item_effects;

CREATE TABLE public.item_effects ( id serial4 NOT NULL, item_id int4 NULL, "name" text NOT NULL, value text NULL, "type" text NULL);


-- public.items definition

-- Drop table

-- DROP TABLE public.items;

CREATE TABLE public.items ( id serial4 NOT NULL, "name" text NOT NULL, description text NULL, icon text NULL, is_usable bool DEFAULT true NOT NULL, CONSTRAINT pk_items_id PRIMARY KEY (id));


-- public.lottery definition

-- Drop table

-- DROP TABLE public.lottery;

CREATE TABLE public.lottery ( id serial4 NOT NULL, user_id int8 NOT NULL);


-- public.marriages definition

-- Drop table

-- DROP TABLE public.marriages;

CREATE TABLE public.marriages ( spouse_a int8 NOT NULL, spouse_b int8 NOT NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT chk_marriage_order CHECK ((spouse_a < spouse_b)), CONSTRAINT pk_marriages PRIMARY KEY (spouse_a, spouse_b));
CREATE INDEX idx_marriages_lookup ON public.marriages USING btree (spouse_a, spouse_b);

-- Table Triggers

create trigger trg_check_marriage before
insert
    on
    public.marriages for each row execute function fn_check_marriage();


-- public.mine definition

-- Drop table

-- DROP TABLE public.mine;

CREATE TABLE public.mine ( server_id int8 NOT NULL, last_reset timestamp DEFAULT now() NULL, item_id int4 NULL, remaining int8 DEFAULT 100000 NOT NULL, CONSTRAINT mine_pkey PRIMARY KEY (server_id));


-- public.otp_sessions definition

-- Drop table

-- DROP TABLE public.otp_sessions;

CREATE TABLE public.otp_sessions ( user_id int8 NOT NULL, otp text NOT NULL, session_token text NULL, created_at timestamp DEFAULT now() NULL, expires_at timestamp NOT NULL, used bool DEFAULT false NULL, CONSTRAINT otp_sessions_pkey PRIMARY KEY (user_id));


-- public.parents definition

-- Drop table

-- DROP TABLE public.parents;

CREATE TABLE public.parents ( child_id int8 NOT NULL, parent_id int8 NOT NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT chk_no_self_parent CHECK ((child_id <> parent_id)), CONSTRAINT pk_parents PRIMARY KEY (child_id));
CREATE INDEX idx_parents_parent ON public.parents USING btree (parent_id);

-- Table Triggers

create trigger trg_check_parents before
insert
    or
update
    on
    public.parents for each row execute function fn_check_parents();


-- public.recipes definition

-- Drop table

-- DROP TABLE public.recipes;

CREATE TABLE public.recipes ( id serial4 NOT NULL, energy_cost int4 DEFAULT 0 NULL, mood_cost int4 DEFAULT 0 NULL, "name" text DEFAULT ''::text NOT NULL, description text NULL, CONSTRAINT recipes_pkey PRIMARY KEY (id));


-- public.shop_pool definition

-- Drop table

-- DROP TABLE public.shop_pool;

CREATE TABLE public.shop_pool ( id bigserial NOT NULL, item_id int8 NULL, price_min int8 NOT NULL, price_max int8 NOT NULL, stock_min int8 NULL, stock_max int8 NOT NULL);


-- public.spending_hourly definition

-- Drop table

-- DROP TABLE public.spending_hourly;

CREATE TABLE public.spending_hourly ( id serial4 NOT NULL, "day" date NOT NULL, "hour" int4 NOT NULL, total_spent int8 DEFAULT 0 NULL, CONSTRAINT spending_hourly_day_hour_key UNIQUE (day, hour), CONSTRAINT spending_hourly_hour_check CHECK (((hour >= 0) AND (hour < 24))), CONSTRAINT spending_hourly_pkey PRIMARY KEY (id));


-- public.trades definition

-- Drop table

-- DROP TABLE public.trades;

CREATE TABLE public.trades ( id serial4 NOT NULL, offerer_id int8 NOT NULL, item_id int4 NULL, quantity int8 NULL, price int8 DEFAULT 0 NOT NULL, created_at timestamp DEFAULT now() NOT NULL, stock int8 DEFAULT 0 NULL, CONSTRAINT trades_pk PRIMARY KEY (id));


-- public.trigger_players definition

-- Drop table

-- DROP TABLE public.trigger_players;

CREATE TABLE public.trigger_players ( id serial4 NOT NULL, session_id int4 NULL, user_id int8 NOT NULL, trigger_word text NOT NULL, last_active_at timestamp NULL, failed_at timestamp NULL);


-- public.trigger_sessions definition

-- Drop table

-- DROP TABLE public.trigger_sessions;

CREATE TABLE public.trigger_sessions ( id serial4 NOT NULL, guild_id int8 NOT NULL, prize int4 NULL, creator_id int8 NOT NULL, inactivity_timeout int4 NULL, length_min int4 NULL, length_max int4 NULL, is_started bool NULL, created_at timestamp NULL);


-- public."user" definition

-- Drop table

-- DROP TABLE public."user";

CREATE TABLE public."user" ( id text NOT NULL, email text NOT NULL, "emailVerified" bool DEFAULT false NOT NULL, "name" text NOT NULL, "createdAt" timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL, "updatedAt" timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL, image text NULL, CONSTRAINT user_email_key UNIQUE (email), CONSTRAINT user_pkey PRIMARY KEY (id));


-- public.user_config definition

-- Drop table

-- DROP TABLE public.user_config;

CREATE TABLE public.user_config ( user_id int8 NOT NULL, todo_capacity int4 DEFAULT 100 NOT NULL, created_at timestamptz DEFAULT now() NULL, public_opt_in bool DEFAULT true NOT NULL, locale text DEFAULT '"en"'::text NULL, CONSTRAINT user_config_pkey PRIMARY KEY (user_id));


-- public.user_effects definition

-- Drop table

-- DROP TABLE public.user_effects;

CREATE TABLE public.user_effects ( id serial4 NOT NULL, "name" text NOT NULL, icon varchar NOT NULL, description text DEFAULT '"No description"'::text NOT NULL, CONSTRAINT user_effects_pk PRIMARY KEY (id));


-- public.user_mining definition

-- Drop table

-- DROP TABLE public.user_mining;

CREATE TABLE public.user_mining ( server_id int8 NOT NULL, user_id int8 NOT NULL, "depth" int4 DEFAULT 0 NULL, CONSTRAINT user_mining_server_id_user_id_key UNIQUE (server_id, user_id));


-- public.users definition

-- Drop table

-- DROP TABLE public.users;

CREATE TABLE public.users ( id int8 NOT NULL, coins int8 NULL, energy int8 NULL, energy_max int8 NOT NULL, mood_max int8 NULL, mood int8 NOT NULL);

-- Table Triggers

create trigger clamp_coins_trigger before
insert
    or
update
    on
    public.users for each row execute function clamp_coins();


-- public.verification definition

-- Drop table

-- DROP TABLE public.verification;

CREATE TABLE public.verification ( id text NOT NULL, identifier text NOT NULL, value text NOT NULL, "expiresAt" timestamp NOT NULL, "createdAt" timestamp DEFAULT CURRENT_TIMESTAMP NULL, "updatedAt" timestamp DEFAULT CURRENT_TIMESTAMP NULL, CONSTRAINT verification_pkey PRIMARY KEY (id));


-- public.wordchain_players definition

-- Drop table

-- DROP TABLE public.wordchain_players;

CREATE TABLE public.wordchain_players ( id serial4 NOT NULL, session_id int4 NOT NULL, user_id int8 NOT NULL, time_left int4 NOT NULL, player_order int4 NOT NULL, eliminated bool NOT NULL, joined_at timestamp NOT NULL);


-- public.wordchain_sessions definition

-- Drop table

-- DROP TABLE public.wordchain_sessions;

CREATE TABLE public.wordchain_sessions ( id serial4 NOT NULL, guild_id int8 NOT NULL, creator_id int8 NOT NULL, created_at timestamp NOT NULL, given_time int4 NOT NULL, max_players int4 NOT NULL, status varchar(20) NULL, current_player_id int4 NULL, last_word text NULL);


-- public.wordchain_words definition

-- Drop table

-- DROP TABLE public.wordchain_words;

CREATE TABLE public.wordchain_words ( id serial4 NOT NULL, session_id int4 NOT NULL, player_id int4 NOT NULL, user_id int8 NOT NULL, word text NOT NULL, created_at timestamp NOT NULL, "valid" bool NOT NULL);


-- public.account definition

-- Drop table

-- DROP TABLE public.account;

CREATE TABLE public.account ( id text NOT NULL, "accountId" text NOT NULL, "providerId" text NOT NULL, "userId" text NOT NULL, "accessToken" text NULL, "refreshToken" text NULL, "idToken" text NULL, "accessTokenExpiresAt" timestamp NULL, "refreshTokenExpiresAt" timestamp NULL, "scope" text NULL, "password" text NULL, "createdAt" timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL, "updatedAt" timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL, CONSTRAINT account_pkey PRIMARY KEY (id), CONSTRAINT "account_userId_fkey" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE);


-- public.current_effects definition

-- Drop table

-- DROP TABLE public.current_effects;

CREATE TABLE public.current_effects ( id serial4 NOT NULL, user_id int8 NOT NULL, effect_id int8 NOT NULL, ticks int8 DEFAULT 0 NOT NULL, applied_at timestamp DEFAULT now() NOT NULL, duration int8 DEFAULT 0 NOT NULL, CONSTRAINT current_effects_pkey PRIMARY KEY (user_id, effect_id), CONSTRAINT current_effects_user_effects_fk FOREIGN KEY (effect_id) REFERENCES public.user_effects(id) ON DELETE CASCADE);


-- public.item_weapons definition

-- Drop table

-- DROP TABLE public.item_weapons;

CREATE TABLE public.item_weapons ( item_id int4 NOT NULL, damage_min int4 NOT NULL, damage_max int4 NOT NULL, crit_rate float8 DEFAULT 0.0 NULL, weapon_type text NOT NULL, break_chance float8 DEFAULT 0.0 NULL, needs_ammo bool DEFAULT false NULL, ammo_item_id int4 NULL, mag_capacity int4 DEFAULT 1 NULL, CONSTRAINT item_weapons_pkey PRIMARY KEY (item_id), CONSTRAINT item_weapons_ammo_item_id_fkey FOREIGN KEY (ammo_item_id) REFERENCES public.items(id), CONSTRAINT item_weapons_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.items(id));


-- public.recipe_require_items definition

-- Drop table

-- DROP TABLE public.recipe_require_items;

CREATE TABLE public.recipe_require_items ( recipe_id int4 NOT NULL, item_id int4 NOT NULL, quantity int4 NOT NULL, is_consumed bool DEFAULT true NOT NULL, CONSTRAINT recipe_require_items_pkey PRIMARY KEY (recipe_id, item_id), CONSTRAINT recipe_require_items_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.items(id), CONSTRAINT recipe_require_items_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES public.recipes(id) ON DELETE CASCADE);


-- public.recipe_results definition

-- Drop table

-- DROP TABLE public.recipe_results;

CREATE TABLE public.recipe_results ( recipe_id int4 NOT NULL, item_id int4 NOT NULL, quantity int4 NOT NULL, CONSTRAINT recipe_results_pkey PRIMARY KEY (recipe_id, item_id), CONSTRAINT recipe_results_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.items(id), CONSTRAINT recipe_results_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES public.recipes(id) ON DELETE CASCADE);


-- public."session" definition

-- Drop table

-- DROP TABLE public."session";

CREATE TABLE public."session" ( id text NOT NULL, "expiresAt" timestamp NOT NULL, "token" text NOT NULL, "createdAt" timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL, "updatedAt" timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL, "ipAddress" text NULL, "userAgent" text NULL, "userId" text NOT NULL, CONSTRAINT session_pkey PRIMARY KEY (id), CONSTRAINT session_token_key UNIQUE (token), CONSTRAINT "session_userId_fkey" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE);


-- public.todo definition

-- Drop table

-- DROP TABLE public.todo;

CREATE TABLE public.todo ( id serial4 NOT NULL, user_id int8 NOT NULL, title text NOT NULL, deadline timestamptz NOT NULL, base_size int4 NOT NULL, growth_rate float8 NOT NULL, penalty_enabled bool DEFAULT false NULL, completed bool DEFAULT false NULL, created_at timestamptz DEFAULT now() NULL, CONSTRAINT todo_pkey PRIMARY KEY (id), CONSTRAINT todo_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_config(user_id) ON DELETE CASCADE);


-- public.trade_quests definition

-- Drop table

-- DROP TABLE public.trade_quests;

CREATE TABLE public.trade_quests ( id serial4 NOT NULL, trust_level int4 NULL, item_id int4 NULL, item_amount int4 NOT NULL, payout int8 NOT NULL, expires_at timestamp NOT NULL, created_at timestamp DEFAULT now() NULL, CONSTRAINT trade_quests_pkey PRIMARY KEY (id), CONSTRAINT trade_quests_trust_level_check CHECK (((trust_level >= 1) AND (trust_level <= 9))), CONSTRAINT trade_quests_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.items(id));