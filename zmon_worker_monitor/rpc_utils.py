#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Server module for exposing an rpc interface for clients to remotely control a local ProcessManager
"""

import inspect
import json
import xmlrpc.client
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler

import logging


class RpcProxy(object):
    """
    This is a base class to subclass in order to expose an instance object through remote RPC
    It serves as a container for some idiosyncrasies of Python XML_RPC
    like the private methods: _listMethods , _methodHelp and _dispatch, which purpose isn't obvious at firsts.
    Here we try to take advantage of these idiosyncrasies.
    """

    exposed_obj_class = object    # override with the class of the object to expose
    valid_methods = []            # override with the list of methods you want to call from RPC

    def __init__(self, exposed_obj):
        assert type(exposed_obj) is self.exposed_obj_class, "Error in RpcProxy: exposed_obj is not declared class"
        self.exposed_obj = exposed_obj
        self.logger = logging.getLogger(__name__)

    def _listMethods(self):
        # this method must be present for system.listMethods to work
        return self.valid_methods

    def _methodHelp(self, method):
        # Override this method for system.methodHelp to work
        if method == 'example_method':
            return "example_method(2,3) => 5"
        else:
            # By convention, return empty string if no help is available
            return ""

    def get_exposed_obj(self):
        # Never add this method to valid_methods
        return self.exposed_obj

    def on_exit(self):
        # Override this to provide a logic to be executed when server is finishing
        pass

    def signal_termination(self, terminate):
        self._signal_terminate_and_exit = bool(terminate)

    def _dispatch(self, method, params):
        # This method is automatically called by Python's SimpleXMLRPCServer for every incoming rpc call
        if method in self.valid_methods:
            obj = self if hasattr(self, method) else self.exposed_obj
            try:
                kw = {}
                m = getattr(obj, method)

                if len(params) and str(params[-1]).startswith('js:'):
                    # let's try to interpret the last argument as keyword args in json format
                    _kw = json.loads(str(params[-1])[len('js:'):])
                    aspec = inspect.getargspec(m)
                    if isinstance(_kw, dict) and _kw and [k in aspec.args for k in _kw]:
                        params = params[:-1]
                        kw = _kw

                return getattr(obj, method)(*params, **kw)
            except Exception:
                self.logger.exception(
                    'Exception encountered in rpc_server while attempting to call: %s with params: %s ', method, params)
                raise
        else:
            raise Exception('method "%s" is not supported' % method)


def get_rpc_client(endpoint):
    """
    Get an rpc client object to remote server listening at endpoint
    :param endpoint: http://host:port/rpc_path
    :return: rpc_client object
    """
    return xmlrpc.client.ServerProxy(endpoint)


# TODO: move to a method in RpcProxy
def start_RPC_server(host, port, rpc_path, rpc_proxy):
    """
    Starts the RPC server and expose some methods of rpc_proxy
    :param host:
    :param port:
    :param rpc_proxy:
    :return:
    """
    # Restrict to a particular path.
    class RequestHandler(SimpleXMLRPCRequestHandler):
        # default path was "RPC2"
        rpc_paths = ('/' + rpc_path.lstrip('/'), )

    logger = logging.getLogger(__name__)
    logger.info('Starting RPC server on http://%s:%d%s ..', host, port, rpc_path)
    server = SimpleXMLRPCServer((host, port), requestHandler=RequestHandler, allow_none=True, logRequests=False)
    server.register_introspection_functions()

    server.register_instance(rpc_proxy)

    try:
        # Run the server's main loop
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("RPC Server loop interrupted: Clean up and propagate SystemExit exception")
        rpc_proxy.on_exit()
        raise
