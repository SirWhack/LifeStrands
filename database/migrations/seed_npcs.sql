-- Seed sample NPCs for development
-- Requires: npcs table exists (run make migrate)

INSERT INTO npcs (
  id, name, location, faction, status,
  background_occupation, background_age,
  personality_traits, life_strand_data, created_at, updated_at
) VALUES (
  '11111111-1111-1111-1111-111111111111',
  'Elena Rodriguez',
  'Coastal Research Station',
  'Research',
  'active',
  'Marine Biologist',
  32,
  json_build_array('curious','methodical','passionate'),
  json_build_object(
    'schema_version','1.0',
    'name','Elena Rodriguez',
    'background', json_build_object('age',32,'occupation','Marine Biologist','location','Coastal Research Station','history','Grew up by the ocean.'),
    'personality', json_build_object(
      'traits', json_build_array('curious','methodical','passionate'),
      'motivations', json_build_array('ocean conservation','scientific discovery'),
      'fears', json_build_array('funding cuts')
    ),
    'current_status', json_build_object('mood','focused','health','good','energy','high','location','Coastal Research Station','activity','field analysis'),
    'relationships', json_build_object(),
    'knowledge', json_build_array(),
    'memories', json_build_array(),
    'status','active'
  ),
  now(), now()
), (
  '22222222-2222-2222-2222-222222222222',
  'Marcus Lee',
  'Tech District',
  'Civilians',
  'active',
  'Software Engineer',
  28,
  json_build_array('analytical','creative','introverted'),
  json_build_object(
    'schema_version','1.0',
    'name','Marcus Lee',
    'background', json_build_object('age',28,'occupation','Software Engineer','location','Tech District','history','Enjoys building tools and learning.'),
    'personality', json_build_object(
      'traits', json_build_array('analytical','creative','introverted'),
      'motivations', json_build_array('building innovative software','learning new technologies'),
      'fears', json_build_array('technical obsolescence')
    ),
    'current_status', json_build_object('mood','focused','health','good','energy','medium','location','Tech District','activity','coding'),
    'relationships', json_build_object(),
    'knowledge', json_build_array(),
    'memories', json_build_array(),
    'status','active'
  ),
  now(), now()
)
ON CONFLICT (id) DO NOTHING;

