#!/usr/bin/env python3
"""
Test script for Life Strands NPC service
"""
import asyncio
import json
import aiohttp
import sys

async def test_npc_service():
    """Test the NPC service endpoints"""
    base_url = "http://localhost:8003"
    
    async with aiohttp.ClientSession() as session:
        print("🧪 Testing Life Strands NPC Service")
        print("=" * 50)
        
        # Test 1: Stats endpoint (bypasses health check)
        print("\n1. Testing /stats endpoint...")
        try:
            async with session.get(f"{base_url}/stats") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Stats: {json.dumps(data, indent=2)}")
                else:
                    text = await response.text()
                    print(f"❌ Stats failed: {response.status} - {text}")
        except Exception as e:
            print(f"❌ Stats error: {e}")
        
        # Test 2: List NPCs
        print("\n2. Testing /npcs endpoint...")
        try:
            async with session.get(f"{base_url}/npcs") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ NPCs list: {json.dumps(data, indent=2)}")
                else:
                    text = await response.text()
                    print(f"❌ NPCs list failed: {response.status} - {text}")
        except Exception as e:
            print(f"❌ NPCs list error: {e}")
        
        # Test 3: Create a test NPC
        print("\n3. Testing NPC creation...")
        test_npc = {
            "life_strand": {
                "name": "Test Warrior",
                "background": {
                    "age": 25,
                    "occupation": "Knight",
                    "location": "Castle Grounds",
                    "history": "A brave knight defending the realm"
                },
                "personality": {
                    "traits": ["brave", "loyal", "protective"],
                    "motivations": ["protect the innocent"],
                    "fears": ["failure"],
                    "values": ["honor", "duty"]
                },
                "current_status": {
                    "mood": "determined",
                    "health": "excellent",
                    "energy": "high",
                    "location": "Training Yard",
                    "activity": "sword practice"
                },
                "relationships": {},
                "knowledge": [],
                "memories": []
            }
        }
        
        try:
            async with session.post(
                f"{base_url}/npc", 
                json=test_npc,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    npc_id = data.get("npc_id")
                    print(f"✅ Created NPC: {npc_id}")
                    
                    # Test 4: Get the created NPC
                    print("\n4. Testing NPC retrieval...")
                    async with session.get(f"{base_url}/npc/{npc_id}") as get_response:
                        if get_response.status == 200:
                            npc_data = await get_response.json()
                            print(f"✅ Retrieved NPC: {npc_data.get('name')}")
                            
                            # Test 5: Get NPC for prompt
                            print("\n5. Testing NPC prompt format...")
                            async with session.get(f"{base_url}/npc/{npc_id}/prompt") as prompt_response:
                                if prompt_response.status == 200:
                                    prompt_data = await prompt_response.json()
                                    print(f"✅ Prompt data: {json.dumps(prompt_data, indent=2)}")
                                else:
                                    text = await prompt_response.text()
                                    print(f"❌ Prompt failed: {prompt_response.status} - {text}")
                        else:
                            text = await get_response.text()
                            print(f"❌ Retrieval failed: {get_response.status} - {text}")
                else:
                    text = await response.text()
                    print(f"❌ Creation failed: {response.status} - {text}")
        except Exception as e:
            print(f"❌ Creation error: {e}")
        
        print("\n" + "=" * 50)
        print("🧪 NPC Service testing complete!")

if __name__ == "__main__":
    asyncio.run(test_npc_service())