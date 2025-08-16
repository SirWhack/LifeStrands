import React from 'react';
import { AppBar, Toolbar, Typography, Button, Box } from '@mui/material';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import ChatIcon from '@mui/icons-material/Chat';
import GroupIcon from '@mui/icons-material/Group';

const Navigation: React.FC = () => {
  const location = useLocation();

  return (
    <AppBar position="static">
      <Toolbar>
        <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
          Life Strands Chat
        </Typography>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            color="inherit"
            component={RouterLink}
            to="/chat"
            startIcon={<ChatIcon />}
            variant={location.pathname === '/chat' || location.pathname === '/' ? 'outlined' : 'text'}
          >
            Chat
          </Button>
          <Button
            color="inherit"
            component={RouterLink}
            to="/npcs"
            startIcon={<GroupIcon />}
            variant={location.pathname === '/npcs' ? 'outlined' : 'text'}
          >
            NPCs
          </Button>
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default Navigation;