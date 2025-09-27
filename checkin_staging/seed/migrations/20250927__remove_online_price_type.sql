-- Migration: remove legacy 'online' price_type rows now that we only track retail prices.
DELETE FROM public.product_prices WHERE price_type = 'online';
