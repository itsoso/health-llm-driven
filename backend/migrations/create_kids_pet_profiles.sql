-- Kids dog space persistent storage in PostgreSQL.
CREATE TABLE IF NOT EXISTS kids_pet_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    breed_id VARCHAR(50) NOT NULL,
    breed_name VARCHAR(100) NOT NULL,
    breed_image VARCHAR(255),
    dog_name VARCHAR(50) NOT NULL,
    hunger INTEGER NOT NULL DEFAULT 100,
    happiness INTEGER NOT NULL DEFAULT 100,
    level INTEGER NOT NULL DEFAULT 1,
    xp INTEGER NOT NULL DEFAULT 0,
    food_bags INTEGER NOT NULL DEFAULT 0,
    has_house BOOLEAN NOT NULL DEFAULT FALSE,
    has_garden BOOLEAN NOT NULL DEFAULT FALSE,
    last_decay_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_interaction_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_kids_pet_profiles_user_id
ON kids_pet_profiles(user_id);
