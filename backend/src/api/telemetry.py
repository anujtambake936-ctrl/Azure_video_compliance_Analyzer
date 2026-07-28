#telemetry  azure open telemetry integration

import os
import logging
 
from azure.monitor.opentelemetry import configure_azure_monitor

#create a dedicated logger

logger=logging.getLogger("brand-gaurdian-telemetry")

def setup_telemetry():
    '''
    initializes Azure monitor Opentelemetry
    track:http requests databases queries,errors,performance metrics
    sends this data to azure monitor

    it auto captures every API requests
    no need to manually log each endpoint
    '''

    #retrieve connection string 

    connection_string=os.getenv("APPLICATION_INSIGHTS_CONNECTION_STRING")

    #CHECK IF CONFIGURED

    if not connection_string:
        logger.warning("no instrumentation key found .telemetry is DISABLED")
        return
    #configure the azure monitor

    try:
        configure_azure_monitor(
            connection_string=connection_string,
            logger_name="brand_guradian_tracer"
        )
        logger.info("Azure Moniotr Tracking Enabled and connected")
    except Exception as e:
        logger.error(f"Failed to Initialize Azure Monitor:{e}")

'''
if we want to which part of sapi is slow 
how many users today

audit endpoint averages 4.s indexer takes 3.8s

error logs show :12% of audits fail due to you tube download errors
metrics like 450 api calls,89 percent success rate
such things are provided by telemetry
'''