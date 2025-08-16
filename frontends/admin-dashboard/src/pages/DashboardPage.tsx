import React from 'react';
import { Container, Typography, Paper, Box, Grid } from '@mui/material';

const DashboardPage: React.FC = () => {
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        System Dashboard
      </Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={6} lg={3}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              System Health
            </Typography>
            <Typography variant="h3" color="success.main">
              ●
            </Typography>
            <Typography variant="body2" color="text.secondary">
              All systems operational
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={6} lg={3}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Active NPCs
            </Typography>
            <Typography variant="h3">
              42
            </Typography>
            <Typography variant="body2" color="text.secondary">
              NPCs in system
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={6} lg={3}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Conversations
            </Typography>
            <Typography variant="h3">
              18
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Active conversations
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={6} lg={3}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              GPU Usage
            </Typography>
            <Typography variant="h3">
              67%
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Memory utilization
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12}>
          <Paper sx={{ p: 4, height: 400 }}>
            <Typography variant="h6" gutterBottom>
              Real-time Monitoring
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <Typography variant="body1" color="text.secondary">
                Real-time charts and monitoring widgets will be implemented here
              </Typography>
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Container>
  );
};

export default DashboardPage;