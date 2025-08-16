import React from 'react';
import { Container, Typography, Paper, Box } from '@mui/material';

const ChatPage: React.FC = () => {
  return (
    <Container maxWidth="lg" sx={{ py: 4, height: '100%' }}>
      <Paper sx={{ p: 4, height: '100%', display: 'flex', flexDirection: 'column' }}>
        <Typography variant="h4" gutterBottom>
          Chat Interface
        </Typography>
        <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Typography variant="h6" color="text.secondary">
            Chat interface will be implemented here
          </Typography>
        </Box>
      </Paper>
    </Container>
  );
};

export default ChatPage;