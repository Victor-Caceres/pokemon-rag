-- Seed data for version_groups
-- INSERT OR IGNORE pattern via ON CONFLICT so this is safe to re-run

INSERT INTO version_groups (name, generation) VALUES
    -- Generation 1
    ('red-blue',                        1),
    ('yellow',                          1),

    -- Generation 2
    ('gold-silver',                     2),
    ('crystal',                         2),

    -- Generation 3
    ('ruby-sapphire',                   3),
    ('emerald',                         3),
    ('firered-leafgreen',               3),

    -- Generation 4
    ('diamond-pearl',                   4),
    ('platinum',                        4),
    ('heartgold-soulsilver',            4),

    -- Generation 5
    ('black-white',                     5),
    ('black-2-white-2',                 5),

    -- Generation 6
    ('x-y',                             6),
    ('omega-ruby-alpha-sapphire',       6),

    -- Generation 7
    ('sun-moon',                        7),
    ('ultra-sun-ultra-moon',            7),
    ('lets-go',                         7),

    -- Generation 8
    ('sword-shield',                    8),
    ('brilliant-diamond-shining-pearl', 8),
    ('legends-arceus',                  8),

    -- Generation 9
    ('scarlet-violet',                  9)

ON CONFLICT (name) DO NOTHING;
